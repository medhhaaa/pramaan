// Shows the time left until `expiresAt` (ISO time from the backend) as m:ss and calls
// onEnd once when it reaches zero. Used for QR / code shares.
import { useEffect, useRef, useState } from "react";

function secondsUntil(expiresAt) {
  return Math.max(0, Math.round((new Date(expiresAt) - Date.now()) / 1000));
}

export default function Countdown({ expiresAt, onEnd }) {
  const [left, setLeft] = useState(() => secondsUntil(expiresAt));
  const ended = useRef(false);

  useEffect(() => {
    ended.current = false;
    const tick = () => {
      const s = secondsUntil(expiresAt);
      setLeft(s);
      if (s === 0 && !ended.current) {
        ended.current = true;
        onEnd?.();
      }
    };
    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, [expiresAt, onEnd]);

  const m = Math.floor(left / 60);
  const s = String(left % 60).padStart(2, "0");
  return <span className="countdown">{left > 0 ? `${m}:${s}` : "ended"}</span>;
}
