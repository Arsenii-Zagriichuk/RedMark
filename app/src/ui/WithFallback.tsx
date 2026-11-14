// An image that swaps to its static fallback if it fails to load (P1-09: both the Drone fix
// and the Target preview fall back to static images).
import { useState } from "react";

export function WithFallback({ src, fallback, alt }: { src: string; fallback: string; alt: string }) {
  const [failed, setFailed] = useState(false);
  return <img src={failed ? fallback : src} alt={alt} onError={() => setFailed(true)} />;
}
