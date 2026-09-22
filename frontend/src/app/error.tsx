"use client";
export default function ErrorPage({ reset }: { reset: () => void }) {
  return (
    <main className="center-state">
      <h1>The console hit an unexpected error.</h1>
      <p>Your incident data is stored on the server.</p>
      <button className="primary" onClick={reset}>
        Reload console
      </button>
    </main>
  );
}
