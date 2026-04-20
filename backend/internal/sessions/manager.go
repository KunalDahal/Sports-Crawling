package sessions

import (
	"bufio"
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"sync"
	"time"
)

const maxEventsPerSession = 1200

type StartRequest struct {
	Keyword  string `json:"keyword"`
	APIKey   string `json:"api_key"`
	DBName   string `json:"db_name"`
	MongoURI string `json:"mongo_uri"`
	ProxyURL string `json:"proxy_url"`
}

type Event struct {
	Type      string         `json:"type"`
	SessionID string         `json:"session_id"`
	Data      map[string]any `json:"data"`
	TS        string         `json:"ts"`
}

type Summary struct {
	ID                   string    `json:"id"`
	CrawlerSessionID     string    `json:"crawler_session_id,omitempty"`
	Keyword              string    `json:"keyword"`
	Status               string    `json:"status"`
	StartedAt            time.Time `json:"started_at"`
	FinishedAt           time.Time `json:"finished_at,omitempty"`
	Events               int       `json:"events"`
	PagesCrawled         int       `json:"pages_crawled"`
	StreamsFound         int       `json:"streams_found"`
	CurrentURL           string    `json:"current_url,omitempty"`
	LastEventType        string    `json:"last_event_type,omitempty"`
	LastError            string    `json:"last_error,omitempty"`
	SearchResults        int       `json:"search_results"`
	CandidatesRegistered int       `json:"candidates_registered"`
}

type Session struct {
	mu          sync.RWMutex
	summary     Summary
	events      []Event
	subscribers map[chan Event]struct{}
	cancel      context.CancelFunc
	cmd         *exec.Cmd
}

type Manager struct {
	mu       sync.RWMutex
	sessions map[string]*Session
}

func NewManager() *Manager {
	return &Manager{sessions: map[string]*Session{}}
}

func (m *Manager) Start(req StartRequest) (*Summary, error) {
	req.Keyword = strings.TrimSpace(req.Keyword)
	if req.Keyword == "" {
		return nil, errors.New("keyword is required")
	}
	if req.DBName == "" {
		req.DBName = "spcrawler"
	}
	if req.MongoURI == "" {
		req.MongoURI = "mongodb://localhost:27017"
	}

	id := newID()
	ctx, cancel := context.WithCancel(context.Background())
	s := &Session{
		summary: Summary{
			ID:        id,
			Keyword:   req.Keyword,
			Status:    "starting",
			StartedAt: time.Now().UTC(),
		},
		subscribers: map[chan Event]struct{}{},
		cancel:      cancel,
	}

	m.mu.Lock()
	m.sessions[id] = s
	m.mu.Unlock()

	if err := s.launch(ctx, req); err != nil {
		m.mu.Lock()
		delete(m.sessions, id)
		m.mu.Unlock()
		cancel()
		return nil, err
	}

	snapshot := s.Summary()
	return &snapshot, nil
}

func (m *Manager) List() []Summary {
	m.mu.RLock()
	defer m.mu.RUnlock()

	out := make([]Summary, 0, len(m.sessions))
	for _, s := range m.sessions {
		out = append(out, s.Summary())
	}
	return out
}

func (m *Manager) Get(id string) (*Session, bool) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	s, ok := m.sessions[id]
	return s, ok
}

func (m *Manager) Stop(id string) bool {
	s, ok := m.Get(id)
	if !ok {
		return false
	}
	s.Stop()
	return true
}

func (m *Manager) Shutdown() {
	m.mu.RLock()
	defer m.mu.RUnlock()
	for _, s := range m.sessions {
		s.Stop()
	}
}

func (s *Session) launch(ctx context.Context, req StartRequest) error {
	script, err := runnerPath()
	if err != nil {
		return err
	}

	python := "python"
	if runtime.GOOS != "windows" {
		python = "python3"
	}

	cmd := exec.CommandContext(ctx, python, "-u", script)
	stdin, err := cmd.StdinPipe()
	if err != nil {
		return err
	}
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		return err
	}
	stderr, err := cmd.StderrPipe()
	if err != nil {
		return err
	}

	if err := cmd.Start(); err != nil {
		return err
	}

	s.mu.Lock()
	s.cmd = cmd
	s.summary.Status = "running"
	s.mu.Unlock()

	go func() {
		defer stdin.Close()
		_ = json.NewEncoder(stdin).Encode(req)
	}()
	go s.scanStdout(stdout)
	go s.scanStderr(stderr)
	go s.wait(cmd)
	return nil
}

func (s *Session) Summary() Summary {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.summary
}

func (s *Session) Events() []Event {
	s.mu.RLock()
	defer s.mu.RUnlock()
	out := make([]Event, len(s.events))
	copy(out, s.events)
	return out
}

func (s *Session) Subscribe() (chan Event, func()) {
	ch := make(chan Event, 128)
	s.mu.Lock()
	s.subscribers[ch] = struct{}{}
	s.mu.Unlock()

	unsubscribe := func() {
		s.mu.Lock()
		if _, ok := s.subscribers[ch]; ok {
			delete(s.subscribers, ch)
			close(ch)
		}
		s.mu.Unlock()
	}
	return ch, unsubscribe
}

func (s *Session) Stop() {
	s.cancel()
	s.mu.Lock()
	if s.summary.Status == "running" || s.summary.Status == "starting" {
		s.summary.Status = "stopping"
	}
	s.mu.Unlock()
}

func (s *Session) scanStdout(r io.Reader) {
	scanner := bufio.NewScanner(r)
	scanner.Buffer(make([]byte, 0, 64*1024), 2*1024*1024)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" {
			continue
		}

		var event Event
		if err := json.Unmarshal([]byte(line), &event); err != nil {
			s.recordInternalError("invalid_runner_event", err.Error())
			continue
		}
		s.addEvent(event)
	}
	if err := scanner.Err(); err != nil {
		s.recordInternalError("runner_stdout", err.Error())
	}
}

func (s *Session) scanStderr(r io.Reader) {
	scanner := bufio.NewScanner(r)
	for scanner.Scan() {
		msg := strings.TrimSpace(scanner.Text())
		if msg != "" {
			s.recordInternalError("runner_stderr", msg)
		}
	}
}

func (s *Session) wait(cmd *exec.Cmd) {
	err := cmd.Wait()

	s.mu.Lock()
	defer s.mu.Unlock()
	if s.summary.Status == "stopping" {
		s.summary.Status = "stopped"
	} else if err != nil {
		s.summary.Status = "failed"
		s.summary.LastError = err.Error()
	} else if s.summary.Status != "finished" {
		s.summary.Status = "finished"
	}
	if s.summary.FinishedAt.IsZero() {
		s.summary.FinishedAt = time.Now().UTC()
	}
}

func (s *Session) addEvent(event Event) {
	s.mu.Lock()
	defer s.mu.Unlock()

	if event.TS == "" {
		event.TS = time.Now().UTC().Format(time.RFC3339Nano)
	}

	s.events = append(s.events, event)
	if len(s.events) > maxEventsPerSession {
		s.events = s.events[len(s.events)-maxEventsPerSession:]
	}

	s.summary.Events++
	s.summary.LastEventType = event.Type
	if event.SessionID != "" {
		s.summary.CrawlerSessionID = event.SessionID
	}
	s.applyEventLocked(event)

	for ch := range s.subscribers {
		select {
		case ch <- event:
		default:
		}
	}
}

func (s *Session) applyEventLocked(event Event) {
	data := event.Data
	switch event.Type {
	case "session.created":
		s.summary.Status = "running"
	case "session.finished":
		s.summary.Status = "finished"
		s.summary.FinishedAt = time.Now().UTC()
		s.summary.PagesCrawled = intFrom(data["pages_crawled"], s.summary.PagesCrawled)
		s.summary.StreamsFound = intFrom(data["streams_found"], s.summary.StreamsFound)
	case "search.complete":
		s.summary.SearchResults = intFrom(data["total_results"], s.summary.SearchResults)
	case "search.candidates":
		s.summary.CandidatesRegistered = intFrom(data["total"], s.summary.CandidatesRegistered)
	case "crawl.page_start", "crawl.page_done", "crawl.page_fail", "llm.navigate":
		if url, ok := data["url"].(string); ok {
			s.summary.CurrentURL = url
		}
	case "crawl.tree_done":
		s.summary.PagesCrawled = intFrom(data["pages_crawled"], s.summary.PagesCrawled)
	case "stream.found":
		s.summary.StreamsFound++
	case "error", "runner.error":
		s.summary.LastError = fmt.Sprint(data["error"])
		if s.summary.LastError == "" {
			s.summary.LastError = fmt.Sprint(data["context"])
		}
	}
}

func (s *Session) recordInternalError(context, message string) {
	s.addEvent(Event{
		Type:      "runner.error",
		SessionID: s.summary.CrawlerSessionID,
		TS:        time.Now().UTC().Format(time.RFC3339Nano),
		Data: map[string]any{
			"context": context,
			"error":   message,
		},
	})
}

func runnerPath() (string, error) {
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		return "", errors.New("could not locate backend source")
	}
	return filepath.Clean(filepath.Join(filepath.Dir(file), "..", "..", "scripts", "run_scraper.py")), nil
}

func newID() string {
	var b [8]byte
	if _, err := rand.Read(b[:]); err != nil {
		return fmt.Sprintf("%d", time.Now().UnixNano())
	}
	return hex.EncodeToString(b[:])
}

func intFrom(value any, fallback int) int {
	switch v := value.(type) {
	case float64:
		return int(v)
	case int:
		return v
	case json.Number:
		n, err := v.Int64()
		if err == nil {
			return int(n)
		}
	}
	return fallback
}
