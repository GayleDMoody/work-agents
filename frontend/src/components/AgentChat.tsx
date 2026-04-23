import { useState, useRef, useEffect } from 'react';
import { Send, Trash2, Loader2 } from 'lucide-react';
import { api } from '../api/client';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
}

interface Props {
  agentId: string;
  agentName: string;
  agentRole: string;
  color: string;
}

const AGENT_GREETINGS: Record<string, string> = {
  product: "Hi! I'm your Product Analyst. I can help analyze requirements, write acceptance criteria, and identify gaps in ticket descriptions. What would you like to work on?",
  pm: "Hello! I'm the Project Manager agent. I can help create execution plans, break down complex tasks, and coordinate work across the team. What's on your plate?",
  architect: "Hey there! I'm the Software Architect. I can help design technical solutions, define interfaces, and plan system architecture. What are we building?",
  frontend: "Hi! I'm the Frontend Developer. I specialize in React and TypeScript. I can write components, debug UI issues, or discuss frontend architecture. What do you need?",
  backend: "Hello! I'm the Backend Developer. I write Python APIs, services, and data models. I can help with endpoint design, database queries, or debugging. What's up?",
  qa: "Hi! I'm the QA Engineer. I write test plans, automated tests, and help catch edge cases. I can review code for testability too. What should we test?",
  devops: "Hey! I'm the DevOps Engineer. I handle CI/CD, Docker, deployment configs, and infrastructure. Need help with your pipeline or deployment setup?",
  code_review: "Hello! I'm the Code Reviewer. I can review your code for quality, security, performance, and maintainability. Paste some code or describe what you'd like reviewed.",
};

export default function AgentChat({ agentId, agentName, agentRole, color }: Props) {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: 'assistant',
      content: AGENT_GREETINGS[agentId] || `Hi! I'm ${agentName}. How can I help?`,
      timestamp: new Date().toISOString(),
    },
  ]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    inputRef.current?.focus();
  }, [agentId]);

  const handleSend = async () => {
    const text = input.trim();
    if (!text || sending) return;

    const userMsg: Message = { role: 'user', content: text, timestamp: new Date().toISOString() };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setSending(true);

    try {
      const res = await api.sendMessage(agentId, text);
      const assistantMsg: Message = { role: 'assistant', content: res.response, timestamp: res.timestamp };
      setMessages(prev => [...prev, assistantMsg]);
    } catch {
      const errorMsg: Message = {
        role: 'assistant',
        content: `I couldn't reach the API. Make sure the backend server is running on port 8000 and your Anthropic API key is configured.`,
        timestamp: new Date().toISOString(),
      };
      setMessages(prev => [...prev, errorMsg]);
    }
    setSending(false);
  };

  const handleClear = () => {
    setMessages([{
      role: 'assistant',
      content: AGENT_GREETINGS[agentId] || `Hi! I'm ${agentName}. How can I help?`,
      timestamp: new Date().toISOString(),
    }]);
    api.clearChat(agentId).catch(() => {});
  };

  return (
    <div className="chat-container">
      {/* Chat header */}
      <div className="chat-header">
        <div className="chat-agent-info">
          <div className="chat-agent-avatar" style={{ background: color }}>{agentName[0]}</div>
          <div>
            <div className="chat-agent-name" style={{ color }}>{agentName}</div>
            <div className="chat-agent-role">{agentRole}</div>
          </div>
        </div>
        <button className="btn btn-outline" onClick={handleClear} title="Clear conversation" style={{ padding: '6px 10px' }}>
          <Trash2 size={14} />
        </button>
      </div>

      {/* Messages */}
      <div className="chat-messages">
        {messages.map((msg, i) => (
          <div key={i} className={`chat-msg chat-msg--${msg.role}`}>
            {msg.role === 'assistant' && (
              <div className="chat-msg-avatar" style={{ background: color }}>{agentName[0]}</div>
            )}
            <div className={`chat-msg-bubble ${msg.role === 'user' ? 'chat-msg-bubble--user' : 'chat-msg-bubble--agent'}`}>
              <div className="chat-msg-text">{msg.content}</div>
              <div className="chat-msg-time">
                {new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </div>
            </div>
          </div>
        ))}
        {sending && (
          <div className="chat-msg chat-msg--assistant">
            <div className="chat-msg-avatar" style={{ background: color }}>{agentName[0]}</div>
            <div className="chat-msg-bubble chat-msg-bubble--agent chat-typing">
              <span className="typing-dot" />
              <span className="typing-dot" />
              <span className="typing-dot" />
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="chat-input-bar">
        <input
          ref={inputRef}
          className="chat-input"
          placeholder={`Message ${agentName}...`}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && !e.shiftKey && handleSend()}
          disabled={sending}
        />
        <button className="chat-send-btn" onClick={handleSend} disabled={!input.trim() || sending} style={{ background: color }}>
          {sending ? <Loader2 size={18} className="spin" /> : <Send size={18} />}
        </button>
      </div>
    </div>
  );
}
