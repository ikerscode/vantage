import { useEffect } from "react";

import { useToastStore } from "../store/toastStore";

const AUTO_DISMISS_MS = 12_000;

export function ToastStack() {
  const toasts = useToastStore((s) => s.toasts);
  const dismissToast = useToastStore((s) => s.dismissToast);

  return (
    <>
      {toasts.map((toast, i) => (
        <ToastItem
          key={toast.id}
          id={toast.id}
          title={toast.monitorName}
          summary={toast.summary}
          time={toast.time}
          offset={i}
          onDismiss={dismissToast}
        />
      ))}
    </>
  );
}

function ToastItem({
  id,
  title,
  summary,
  time,
  offset,
  onDismiss,
}: {
  id: string;
  title: string;
  summary: string;
  time: string;
  offset: number;
  onDismiss: (id: string) => void;
}) {
  useEffect(() => {
    const timer = setTimeout(() => onDismiss(id), AUTO_DISMISS_MS);
    return () => clearTimeout(timer);
  }, [id, onDismiss]);

  return (
    <div className="toast" style={{ top: `${96 + offset * 92}px` }}>
      <span className="toast-dot" />
      <div className="toast-body">
        <div className="toast-title">Monitor tripped — {title}</div>
        <div className="toast-meta">{summary}</div>
        <div className="toast-time">{time}</div>
      </div>
      <button className="toast-close" onClick={() => onDismiss(id)}>
        ×
      </button>
    </div>
  );
}
