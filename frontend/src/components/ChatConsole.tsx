import React, { useState, useRef, useEffect } from 'react';
import { api } from '../services/api';
import { Send, Loader, User, Bot, ExternalLink } from 'lucide-react';
import ReactMarkdown from 'react-markdown';

interface Message {
  id: string;
  sender: 'user' | 'ai';
  text: string;
  sources?: string[];
}

interface ChatConsoleProps {
  username: string | null;
  indexingStatus: 'not_started' | 'processing' | 'completed' | 'failed';
}

const SUGGESTIONS = [
  "What is the best, most impressive project?",
  "What programming languages and frameworks are used?",
  "Explain the technical details of their top repositories.",
];

export const ChatConsole: React.FC<ChatConsoleProps> = ({ username, indexingStatus }) => {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'welcome',
      sender: 'ai',
      text: "Hello! Ask me any question about the developer's repositories, technical stack, or architecture.",
    },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const chatMessagesRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom of messages
  const scrollToBottom = () => {
    if (chatMessagesRef.current) {
      chatMessagesRef.current.scrollTop = chatMessagesRef.current.scrollHeight;
    }
  };

  useEffect(() => {
    scrollToBottom();
    const timer = setTimeout(scrollToBottom, 50);
    return () => clearTimeout(timer);
  }, [messages, loading]);

  const handleSendMessage = async (textToSend: string) => {
    if (!username || indexingStatus !== 'completed' || !textToSend.trim() || loading) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      sender: 'user',
      text: textToSend.trim(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setLoading(true);

    try {
      const response = await api.askQuestion(username, textToSend.trim());
      const aiMessage: Message = {
        id: (Date.now() + 1).toString(),
        sender: 'ai',
        text: response.answer,
        sources: response.sources,
      };
      setMessages((prev) => [...prev, aiMessage]);
    } catch (err: any) {
      const aiMessage: Message = {
        id: (Date.now() + 1).toString(),
        sender: 'ai',
        text: `Error calling AI service: ${err.message || 'Please check API keys.'}`,
      };
      setMessages((prev) => [...prev, aiMessage]);
    } finally {
      setLoading(false);
    }
  };

  const handleFormSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    handleSendMessage(input);
  };

  const isChatDisabled = !username || indexingStatus !== 'completed';

  return (
    <div className="chat-container glass-panel animate-fade-in">
      <div style={{ padding: '1.25rem 1.5rem', borderBottom: '1px solid var(--border-color)', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
        <Bot size={20} className="glow-text-cyan" style={{ color: 'var(--secondary)' }} />
        <h3 style={{ fontSize: '1.15rem', fontWeight: 700, color: 'var(--text-title)' }}>AI Technical Assistant</h3>
        {username && (
          <span style={{ fontSize: '0.8rem', color: 'var(--text-muted-dim)', marginLeft: 'auto' }}>
            Context: <strong style={{ color: 'var(--secondary)' }}>@{username}</strong>
          </span>
        )}
      </div>

      {/* Messages */}
      <div className="chat-messages" ref={chatMessagesRef}>
        {messages.map((msg) => (
          <div key={msg.id} className={`message-bubble ${msg.sender}`}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', alignSelf: msg.sender === 'user' ? 'flex-end' : 'flex-start', fontSize: '0.75rem', color: 'var(--text-muted-dim)' }}>
              {msg.sender === 'user' ? (
                <>
                  You <User size={12} />
                </>
              ) : (
                <>
                  <Bot size={12} style={{ color: 'var(--secondary)' }} /> AI assistant
                </>
              )}
            </div>
            <div className="message-content">
              {msg.sender === 'user' ? (
                msg.text.split('\n').map((line, idx) => (
                  <p key={idx} style={{ marginBottom: line === '' ? '0.75rem' : '0.25rem' }}>
                    {line}
                  </p>
                ))
              ) : (
                <ReactMarkdown>{msg.text}</ReactMarkdown>
              )}
              
              {/* Citations */}
              {msg.sources && msg.sources.length > 0 && (
                <div className="chat-citations">
                  <span style={{ color: 'var(--text-muted-dim)', marginRight: '0.25rem' }}>Sources:</span>
                  {msg.sources.map((src) => (
                    <a
                      key={src}
                      href={`https://github.com/${username}/${src}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="citation-badge"
                    >
                      {src} <ExternalLink size={10} />
                    </a>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
        {loading && (
          <div className="message-bubble ai">
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.75rem', color: 'var(--text-muted-dim)' }}>
              <Bot size={12} style={{ color: 'var(--secondary)' }} /> AI assistant
            </div>
            <div className="message-content" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Loader size={16} className="animate-spin" style={{ color: 'var(--secondary)' }} />
              Thinking...
            </div>
          </div>
        )}
      </div>

      {/* Suggestion Prompts */}
      {!isChatDisabled && messages.length === 1 && !loading && (
        <div className="chat-suggestions">
          {SUGGESTIONS.map((sug) => (
            <button
              key={sug}
              onClick={() => handleSendMessage(sug)}
              className="btn-suggestion"
            >
              {sug}
            </button>
          ))}
        </div>
      )}

      {/* Input Form */}
      <form onSubmit={handleFormSubmit} className="chat-input-bar">
        <input
          type="text"
          className="chat-input"
          placeholder={
            isChatDisabled
              ? "Analyze a GitHub profile first to start chatting..."
              : "Ask about their architecture, dependencies, algorithms..."
          }
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={isChatDisabled || loading}
        />
        <button
          type="submit"
          className="btn-send"
          disabled={isChatDisabled || !input.trim() || loading}
        >
          <Send size={18} />
        </button>
      </form>
    </div>
  );
};
