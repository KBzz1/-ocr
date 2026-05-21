import { useEffect, useRef } from 'react';

export function useSilentPolling(callback: () => Promise<void> | void, intervalMs: number) {
  const callbackRef = useRef(callback);
  const isPollingRef = useRef(false);

  useEffect(() => {
    callbackRef.current = callback;
  }, [callback]);

  useEffect(() => {
    const intervalId = window.setInterval(() => {
      if (document.visibilityState === 'hidden' || isPollingRef.current) return;

      isPollingRef.current = true;
      Promise.resolve(callbackRef.current()).finally(() => {
        isPollingRef.current = false;
      });
    }, intervalMs);

    return () => window.clearInterval(intervalId);
  }, [intervalMs]);
}
