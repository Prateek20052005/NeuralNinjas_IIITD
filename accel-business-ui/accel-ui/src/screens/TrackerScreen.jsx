import AppHeader from '../components/AppHeader.jsx';
import DecisionCard from '../components/DecisionCard.jsx';
import Timeline from '../components/Timeline.jsx';
import Button from '../components/Button.jsx';
import { Trash2 } from 'lucide-react';

const DECISIONS = {
  approved: {
    title: 'Approved',
    body: 'Your documents are verified.',
    next: 'Technician visit on Fri 17 Jul, 9 am – 12 noon.',
  },
  retake: {
    title: 'Please retake one photo',
    body: "The electricity bill is blurred, so we can't read the address.",
    action: 'Retake electricity bill',
  },
  review: {
    title: 'Being reviewed',
    body: 'A person from our team is checking your documents.',
    next: "Nothing to do now. We'll message you on WhatsApp when it's done.",
  },
  rejected: {
    title: "We can't approve this yet",
    body: "The name on your GST certificate doesn't match the GST registry.",
    next: 'Someone from our team will call you to sort it out.',
    action: 'Talk to a person now',
  },
};

/** decision: 'approved' | 'retake' | 'review' | 'rejected' */
export default function TrackerScreen({ decision = 'approved', onBack, onAction, onDelete, headerActions }) {
  const d = DECISIONS[decision];
  const ok = decision === 'approved';
  const steps = [
    { title: 'Plan accepted', detail: '12 Jul, 10:41 am', state: 'done' },
    { title: 'Consent given', detail: '12 Jul, 10:44 am', state: 'done' },
    { title: 'Documents uploaded', detail: '13 Jul, 10:52 am', state: 'done' },
    { title: 'Documents verified', detail: ok ? '13 Jul, 10:55 am' : d.title, state: ok ? 'done' : 'now' },
    { title: 'Installation booked', detail: ok ? 'Fri 17 Jul, 9 am – 12 noon' : 'After approval', state: ok ? 'now' : 'todo' },
    { title: 'Technician visit', detail: 'Live by 20 Jul', state: 'todo' },
  ];
  return (
    <div className="app-shell">
      <AppHeader title="Your order" onBack={onBack} actions={headerActions} />
      <main className="page" style={{ gap: 20, paddingTop: 16 }}>
        <DecisionCard
          outcome={decision}
          title={d.title}
          body={d.body}
          next={d.next}
          action={
            d.action ? (
              <Button block variant={decision === 'retake' ? 'primary' : 'secondary'} onClick={onAction}>
                {d.action}
              </Button>
            ) : null
          }
        />
        <section className="card">
          <h2 className="section-label" style={{ margin: '0 0 16px' }}>Progress</h2>
          <Timeline steps={steps} />
        </section>
        <Button variant="plain" block icon={Trash2} onClick={onDelete} style={{ color: 'var(--color-danger)' }}>
          Delete my data
        </Button>
        <p className="t-footnote t-secondary" style={{ textAlign: 'center', marginTop: -12 }}>
          Cancels this order and removes your documents and details.
        </p>
      </main>
    </div>
  );
}
