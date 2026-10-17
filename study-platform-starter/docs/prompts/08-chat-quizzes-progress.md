# Phase 8 — Subject Chat, Quizzes, Revision, and Progress

Implement:
- Separate chat history per user and subject; never share private chats by default.
- Source-grounded responses with citations and a visible “sources used” section.
- Quiz creation from authorized subject materials; configurable difficulty and question type.
- Answer checking with explanations and source references. Clearly flag uncertain grading for open-ended answers.
- Revision scheduling/cards and saved study notes.
- Progress dashboard by subject: sessions, time, materials processed, quizzes/accuracy, revision queue.
- Caching for repeated questions where safe; cache key must include subject, permission scope, model/prompt version, and normalized query. Never serve one student's private chat to another.
- Abuse/rate limits, per-user usage budgets, and helpful handling of provider limits.
Tests: private history isolation, cross-subject citation prevention, quiz scoring, cache boundaries, and progress calculations.
