package main

import (
	"log"
	"net/http"
	"os"

	"spcrawler/backend/internal/sessions"
)

func main() {
	addr := getenv("ADDR", ":8080")
	manager := sessions.NewManager()
	defer manager.Shutdown()

	mux := http.NewServeMux()
	sessions.RegisterHandlers(mux, manager)

	log.Printf("spcrawler backend listening on %s", addr)
	if err := http.ListenAndServe(addr, withCORS(mux)); err != nil {
		log.Fatal(err)
	}
}

func getenv(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}

func withCORS(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		next.ServeHTTP(w, r)
	})
}
