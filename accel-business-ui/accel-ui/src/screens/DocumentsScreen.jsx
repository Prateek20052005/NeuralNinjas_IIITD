import { useEffect, useState } from 'react';
import AppHeader from '../components/AppHeader.jsx';
import ProgressIndicator from '../components/ProgressIndicator.jsx';
import UploadTile from '../components/UploadTile.jsx';
import FieldPreviewList from '../components/FieldPreviewList.jsx';
import TextField from '../components/TextField.jsx';
import StatusBadge from '../components/StatusBadge.jsx';
import Note from '../components/Note.jsx';
import Button from '../components/Button.jsx';
import './DocumentsScreen.css';

/** Four upload tiles with instant feedback. Replace the fake reader with your OCR call. */
export default function DocumentsScreen({ onBack, onContinue }) {
  const [docs, setDocs] = useState({
    gst: { state: 'read' },
    udyam: { state: 'empty' },
    bill: { state: 'retake', reason: 'Looks blurred' },
    id: { state: 'reading', progress: 0.3 },
  });

  // Demo only: simulate the ID being read.
  useEffect(() => {
    if (docs.id.state !== 'reading') return undefined;
    const t = setInterval(() => {
      setDocs((d) => {
        const p = d.id.progress + 0.15;
        return { ...d, id: p >= 1 ? { state: 'read' } : { state: 'reading', progress: p } };
      });
    }, 500);
    return () => clearInterval(t);
  }, [docs.id.state]);

  const ready = Object.values(docs).filter((d) => d.state === 'read').length;

  return (
    <div className="app-shell">
      <AppHeader title="Documents" onBack={onBack}>
        <ProgressIndicator current={ready} total={4} formatLabel={(c, t) => `${c} of ${t} ready`} />
      </AppHeader>
      <main className="page" style={{ gap: 20, paddingTop: 20 }}>
        <div>
          <h1 className="t-large-title" style={{ fontSize: '1.875rem' }}>Add 4 photos</h1>
          <p className="t-body t-secondary">We read each one in seconds. If something's unclear, you'll know right away.</p>
        </div>

        {docs.bill.state === 'retake' ? (
          <section className="card ab-retake" role="alert">
            <StatusBadge status="retake">Retake · Electricity bill</StatusBadge>
            <p className="t-headline" style={{ fontSize: '1.1875rem' }}>This looks blurred. Retake it in good light.</p>
            <p className="t-callout t-secondary">Lay the bill flat near a window and hold the phone still. We'll take the photo when it's sharp.</p>
            <Button variant="secondary" block onClick={() => setDocs((d) => ({ ...d, bill: { state: 'read' } }))}>
              Retake photo
            </Button>
          </section>
        ) : null}

        <section className="ab-tiles" aria-label="Your documents">
          <UploadTile name="GST certificate" {...docs.gst} />
          <UploadTile name="Udyam certificate" {...docs.udyam} onSelect={() => setDocs((d) => ({ ...d, udyam: { state: 'reading', progress: 0.1 } }))} />
          <UploadTile name="Electricity bill" sublabel="Address proof" {...docs.bill} />
          <UploadTile name="ID of the signer" {...docs.id} />
        </section>

        <section className="card" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <p className="t-headline">Don't have the Udyam certificate?</p>
          <TextField label="Type its number instead" placeholder="UDYAM-MH-00-0000000" mono hint="We check it with the Udyam registry. No photo needed." autoComplete="off" />
        </section>

        <FieldPreviewList
          title="Found on your GST certificate"
          fields={[
            { label: 'Legal name', value: 'Asha Physio Clinic' },
            { label: 'GSTIN', value: '27XUI4321A1ZP', masked: true },
            { label: 'Address', value: 'Karve Road, Kothrud, Pune 411038' },
            { label: 'Registration', node: <StatusBadge status="approved">Active</StatusBadge> },
          ]}
          footnote="The photo itself has already been deleted."
        />

        <Note tone="trust">Photos are read and then thrown away. ID numbers are always shown masked.</Note>
      </main>
      <div className="ab-docs-bar">
        <Button block disabled={ready < 4} onClick={onContinue}>
          Send for checking
        </Button>
      </div>
    </div>
  );
}
