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
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"sync"
	"time"
)

type StartRequest struct {
	SessionID   string `json:"session_id,omitempty"`
	Description string `json:"description,omitempty"`
	Match       string `json:"match"`
	Link        string `json:"link,omitempty"`
	APIKey      string `json:"api_key"`
	ProxyURL    string `json:"proxy_url"`
}

type Link struct {
	URL   string `json:"url"`
	Title string `json:"title"`
}

type Keyword struct {
	ID            string        `json:"id"`
	Query         string        `json:"query"`
	SearchResults int           `json:"search_results"`
	Status        string        `json:"status,omitempty"`
	StartedAt     string        `json:"started_at,omitempty"`
	FinishedAt    string        `json:"finished_at,omitempty"`
	RootIDs       []string      `json:"root_ids,omitempty"`
	NodeIDs       []string      `json:"node_ids,omitempty"`
	Stats         KeywordStats  `json:"stats,omitempty"`
	Result        KeywordResult `json:"result,omitempty"`
}

type KeywordStats struct {
	Roots      int `json:"roots"`
	Visited    int `json:"visited"`
	Official   int `json:"official"`
	Suspicious int `json:"suspicious"`
	Clean      int `json:"clean"`
}

type KeywordResult struct {
	NodeIDs []string     `json:"node_ids,omitempty"`
	Stats   KeywordStats `json:"stats,omitempty"`
}

type Node struct {
	ID             string   `json:"id"`
	ParentID       string   `json:"parent_id"`
	KeywordID      string   `json:"keyword_id"`
	Root           bool     `json:"root"`
	Depth          int      `json:"depth"`
	URL            string   `json:"url"`
	Title          string   `json:"title"`
	Summary        string   `json:"summary"`
	Links          []Link   `json:"links"`
	Iframes        []string `json:"iframes"`
	StreamURLs     []string `json:"stream_urls"`
	ChildIDs       []string `json:"child_ids"`
	Classification string   `json:"classification"`
	Color          string   `json:"color"`
	Reason         string   `json:"reason"`
	Status         string   `json:"status"`
	Visited        bool     `json:"visited"`
}

type Stats struct {
	Keywords   int `json:"keywords"`
	Roots      int `json:"roots"`
	Visited    int `json:"visited"`
	Official   int `json:"official"`
	Suspicious int `json:"suspicious"`
	Clean      int `json:"clean"`
}

type State struct {
	SessionID       string    `json:"session_id"`
	Match           string    `json:"match"`
	Status          string    `json:"status"`
	Message         string    `json:"message"`
	Error           string    `json:"error"`
	StartedAt       string    `json:"started_at"`
	FinishedAt      string    `json:"finished_at"`
	CurrentNodeID   string    `json:"current_node_id"`
	CurrentURL      string    `json:"current_url"`
	ActiveKeywordID string    `json:"active_keyword_id"`
	Keywords        []Keyword `json:"keywords"`
	Nodes           []Node    `json:"nodes"`
	Stats           Stats     `json:"stats"`
}

type Summary struct {
	ID         string    `json:"id"`
	Match      string    `json:"match"`
	Status     string    `json:"status"`
	StartedAt  time.Time `json:"started_at"`
	FinishedAt time.Time `json:"finished_at,omitempty"`
	CurrentURL string    `json:"current_url,omitempty"`
	Message    string    `json:"message,omitempty"`
	LastError  string    `json:"last_error,omitempty"`
	Keywords   int       `json:"keywords"`
	Roots      int       `json:"roots"`
	Visited    int       `json:"visited"`
	Official   int       `json:"official"`
	Suspicious int       `json:"suspicious"`
	Clean      int       `json:"clean"`
}

type Session struct {
	mu          sync.RWMutex
	summary     Summary
	state       State
	subscribers map[chan State]struct{}
	cancel      context.CancelFunc
	cmd         *exec.Cmd
}

type Manager struct {
	mu         sync.RWMutex
	sessions   map[string]*Session
	venvMu     sync.Mutex
	venvPython string
	venvErr    error
}

func NewManager() *Manager {
	return &Manager{sessions: map[string]*Session{}}
}

func (m *Manager) Start(req StartRequest) (*Summary, error) {
	req.Description = strings.TrimSpace(req.Description)
	req.Match = strings.TrimSpace(req.Match)
	req.Link = strings.TrimSpace(req.Link)
	if req.Match == "" {
		req.Match = req.Description
	}
	if req.Match == "" && req.Link == "" {
		return nil, errors.New("description or link is required")
	}
	if req.Match == "" {
		req.Match = req.Link
	}

	python, err := m.resolveVenvPython()
	if err != nil {
		return nil, fmt.Errorf("python venv setup failed: %w", err)
	}

	id := newID()
	req.SessionID = id

	ctx, cancel := context.WithCancel(context.Background())
	s := &Session{
		summary: Summary{
			ID:        id,
			Match:     req.Match,
			Status:    "starting",
			StartedAt: time.Now().UTC(),
		},
		state: State{
			SessionID: id,
			Match:     req.Match,
			Status:    "starting",
		},
		subscribers: map[chan State]struct{}{},
		cancel:      cancel,
	}

	m.mu.Lock()
	m.sessions[id] = s
	m.mu.Unlock()

	if err := s.launch(ctx, req, python); err != nil {
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

func (m *Manager) Remove(id string) bool {
	s, ok := m.Get(id)
	if !ok {
		return false
	}
	s.Stop()
	m.mu.Lock()
	delete(m.sessions, id)
	m.mu.Unlock()
	return true
}

func (m *Manager) Shutdown() {
	m.mu.RLock()
	defer m.mu.RUnlock()
	for _, s := range m.sessions {
		s.Stop()
	}
}

func (m *Manager) resolveVenvPython() (string, error) {
	if python := strings.TrimSpace(os.Getenv("SPCRAWLER_PYTHON")); python != "" {
		if _, err := exec.LookPath(python); err != nil {
			return "", fmt.Errorf("SPCRAWLER_PYTHON is not executable: %w", err)
		}
		return python, nil
	}

	m.venvMu.Lock()
	defer m.venvMu.Unlock()

	if m.venvPython != "" {
		return m.venvPython, nil
	}
	if m.venvErr != nil {
		return "", m.venvErr
	}

	python, err := ensureVenv()
	if err != nil {
		m.venvErr = err
		return "", err
	}
	m.venvPython = python
	return python, nil
}

func ensureVenv() (string, error) {
	scriptPath, err := runnerPath()
	if err != nil {
		return "", err
	}
	scriptsDir := filepath.Dir(scriptPath)

	venvDir := filepath.Join(scriptsDir, ".venv")
	pythonBin := venvPythonBin(venvDir)

	created := false
	if _, statErr := os.Stat(pythonBin); statErr == nil {
		log.Printf("spcrawler: reusing existing venv at %s", venvDir)
	} else {
		sysPython, err := findSystemPython()
		if err != nil {
			return "", fmt.Errorf("no usable Python found: %w", err)
		}
		log.Printf("spcrawler: creating venv at %s using %s", venvDir, sysPython)

		if out, runErr := runCmd(sysPython, "-m", "venv", venvDir); runErr != nil {
			return "", fmt.Errorf("venv creation failed: %w\n%s", runErr, out)
		}
		created = true
		log.Printf("spcrawler: venv created")
	}

	if out, runErr := runCmd(pythonBin, "-m", "pip", "install", "--quiet", "--upgrade", "pip"); runErr != nil {
		log.Printf("spcrawler: pip upgrade warning: %s", out)
	}

	reqFile := filepath.Join(scriptsDir, "requirements.txt")
	if created {
		if _, statErr := os.Stat(reqFile); statErr == nil {
			log.Printf("spcrawler: installing %s", reqFile)
			out, runErr := runCmd(pythonBin, "-m", "pip", "install", "--quiet", "-r", reqFile)
			if runErr != nil {
				return "", fmt.Errorf("pip install failed: %w\n%s", runErr, out)
			}
			log.Printf("spcrawler: requirements installed")
		}
	}

	engineDir := filepath.Clean(filepath.Join(scriptsDir, "..", "..", "spcrawler"))
	if _, statErr := os.Stat(filepath.Join(engineDir, "pyproject.toml")); statErr == nil {
		log.Printf("spcrawler: installing engine package from %s", engineDir)
		out, runErr := runCmd(pythonBin, "-m", "pip", "install", "--quiet", "--editable", engineDir)
		if runErr != nil {
			return "", fmt.Errorf("engine install failed: %w\n%s", runErr, out)
		}
		log.Printf("spcrawler: engine package installed")
	}

	return pythonBin, nil
}

func venvPythonBin(venvDir string) string {
	if runtime.GOOS == "windows" {
		return filepath.Join(venvDir, "Scripts", "python.exe")
	}
	return filepath.Join(venvDir, "bin", "python")
}

func findSystemPython() (string, error) {
	candidates := []string{"python3", "python"}
	for _, name := range candidates {
		path, err := exec.LookPath(name)
		if err != nil {
			continue
		}
		out, err := exec.Command(path, "-c", "import sys; assert sys.version_info >= (3,8)").CombinedOutput()
		if err != nil {
			log.Printf("spcrawler: skipping %s - %s", path, strings.TrimSpace(string(out)))
			continue
		}
		return path, nil
	}
	return "", errors.New("python3 (>=3.8) not found on PATH")
}

func runCmd(name string, args ...string) (string, error) {
	cmd := exec.Command(name, args...)
	out, err := cmd.CombinedOutput()
	return string(out), err
}

func (s *Session) launch(ctx context.Context, req StartRequest, python string) error {
	script, err := runnerPath()
	if err != nil {
		return err
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
	s.state.Status = "running"
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

func (s *Session) State() State {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.state
}

func (s *Session) Subscribe() (chan State, func()) {
	ch := make(chan State, 32)
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
		s.state.Status = "stopping"
	}
	s.mu.Unlock()
}

func (s *Session) scanStdout(r io.Reader) {
	dec := json.NewDecoder(bufio.NewReader(r))
	for {
		var state State
		if err := dec.Decode(&state); err != nil {
			if errors.Is(err, io.EOF) {
				return
			}
			s.recordInternalError("invalid_runner_state", err.Error())
			return
		}
		s.addState(state)
	}
}

func (s *Session) scanStderr(r io.Reader) {
	scanner := bufio.NewScanner(r)
	scanner.Buffer(make([]byte, 0, 64*1024), 1024*1024)
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
		s.state.Status = "stopped"
	} else if err != nil {
		s.summary.Status = "failed"
		s.summary.LastError = err.Error()
		s.state.Status = "failed"
		if s.state.Error == "" {
			s.state.Error = err.Error()
		}
	} else if s.summary.Status != "finished" {
		s.summary.Status = "finished"
		s.state.Status = "finished"
	}
	if s.summary.FinishedAt.IsZero() {
		s.summary.FinishedAt = time.Now().UTC()
	}
	if s.state.FinishedAt == "" {
		s.state.FinishedAt = s.summary.FinishedAt.Format(time.RFC3339Nano)
	}
	s.broadcastLocked(s.state)
}

func (s *Session) addState(state State) {
	s.mu.Lock()
	defer s.mu.Unlock()

	if state.SessionID == "" {
		state.SessionID = s.summary.ID
	}
	if state.Match == "" {
		state.Match = s.summary.Match
	}
	s.state = state
	s.applyStateLocked(state)
	s.broadcastLocked(state)
}

func (s *Session) applyStateLocked(state State) {
	s.summary.Match = state.Match
	s.summary.Status = state.Status
	s.summary.CurrentURL = state.CurrentURL
	s.summary.Message = state.Message
	s.summary.LastError = state.Error
	s.summary.Keywords = state.Stats.Keywords
	s.summary.Roots = state.Stats.Roots
	s.summary.Visited = state.Stats.Visited
	s.summary.Official = state.Stats.Official
	s.summary.Suspicious = state.Stats.Suspicious
	s.summary.Clean = state.Stats.Clean
	if ts, ok := parseTime(state.StartedAt); ok {
		s.summary.StartedAt = ts
	}
	if ts, ok := parseTime(state.FinishedAt); ok {
		s.summary.FinishedAt = ts
	}
}

func (s *Session) recordInternalError(context, message string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.summary.LastError = fmt.Sprintf("%s: %s", context, message)
	s.state.Error = s.summary.LastError
	s.broadcastLocked(s.state)
}

func (s *Session) broadcastLocked(state State) {
	for ch := range s.subscribers {
		select {
		case ch <- state:
		default:
		}
	}
}

func runnerPath() (string, error) {
	if override := strings.TrimSpace(os.Getenv("SPCRAWLER_RUNNER")); override != "" {
		if filepath.IsAbs(override) {
			return override, nil
		}
		cwd, err := os.Getwd()
		if err != nil {
			return "", err
		}
		return filepath.Clean(filepath.Join(cwd, override)), nil
	}

	exe, err := os.Executable()
	if err == nil {
		candidate := filepath.Clean(filepath.Join(filepath.Dir(exe), "..", "backend", "scripts", "run_scraper.py"))
		if _, statErr := os.Stat(candidate); statErr == nil {
			return candidate, nil
		}
	}

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

func parseTime(value string) (time.Time, bool) {
	if strings.TrimSpace(value) == "" {
		return time.Time{}, false
	}
	ts, err := time.Parse(time.RFC3339Nano, value)
	if err != nil {
		return time.Time{}, false
	}
	return ts, true
}
