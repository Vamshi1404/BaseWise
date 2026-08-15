import { useEffect, useRef, useState } from 'react';

/**
 * Reveals `text` character-by-character, like the AI is typing it.
 * Returns the portion of text currently visible.
 */
export function useTypewriter(text: string, speed = 14): string {
  const [visible, setVisible] = useState('');
  const idxRef = useRef(0);

  useEffect(() => {
    idxRef.current = 0;
    setVisible('');
  }, [text]);

  useEffect(() => {
    if (idxRef.current >= text.length) return;

    const timer = setInterval(() => {
      idxRef.current = Math.min(text.length, idxRef.current + 3);
      setVisible(text.slice(0, idxRef.current));
      if (idxRef.current >= text.length) clearInterval(timer);
    }, speed);

    return () => clearInterval(timer);
  }, [text, speed]);

  return visible;
}
