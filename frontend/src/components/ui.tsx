"use client";
import { useEffect, useRef } from "react";
import { Icon } from "./icon";

export function Badge({ value }: { value: string }) {
  return (
    <span className={`badge ${value.toLowerCase()}`}>
      <span className="dot" />
      {value.replaceAll("_", " ")}
    </span>
  );
}

export function Modal({
  title,
  children,
  onClose,
  drawer = false,
}: {
  title: string;
  children: React.ReactNode;
  onClose: () => void;
  drawer?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    dialog?.showModal();
    return () => dialog?.close();
  }, []);
  return (
    <dialog
      ref={ref}
      className={drawer ? "modal drawer" : "modal"}
      onCancel={onClose}
      aria-label={title}
    >
      <div className="modal-heading">
        <h2>{title}</h2>
        <button className="icon-button" onClick={onClose} aria-label="Close dialog">
          <Icon name="x" />
        </button>
      </div>
      {children}
    </dialog>
  );
}
