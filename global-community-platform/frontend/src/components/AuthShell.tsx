import type { ReactNode } from 'react'
import { MessageCircle, ShieldCheck, Users } from 'lucide-react'

/** Two-column sign-in layout shared by login, register and the account-recovery pages. */
export default function AuthShell({ eyebrow, title, subtitle, children }: { eyebrow: string; title: string; subtitle: ReactNode; children: ReactNode }) {
  return <div className="auth-page">
    <section className="auth-story"><div className="auth-brand"><div className="brand-mark"><MessageCircle size={19} /></div>commonground</div><div className="story-content"><span className="eyebrow light-eyebrow">A SPACE FOR EVERY PERSPECTIVE</span><h1>Better ideas<br />happen <em>together.</em></h1><p>Find your community, ask the big questions, and turn everyday conversations into something meaningful.</p><div className="story-stats"><div><Users size={17} /><span>Communities that connect</span></div><div><MessageCircle size={17} /><span>Conversations that matter</span></div><div><ShieldCheck size={17} /><span>Spaces shaped by people</span></div></div></div><div className="story-footer">Curiosity has a place here. <span>© 2026 CommonGround</span></div></section>
    <section className="auth-panel"><div className="auth-form-wrap"><div className="mobile-auth-brand"><div className="brand-mark"><MessageCircle size={18} /></div>commonground</div><span className="eyebrow">{eyebrow}</span><h2>{title}</h2><p className="auth-subtitle">{subtitle}</p>
      {children}
    </div></section>
  </div>
}
