import React from 'react';

/**
 * Calls `task` now and then every `intervalMs`, until unmount or until `task` changes. A round that
 * is still running when the next tick arrives is not duplicated, and answers that arrive after
 * unmount are dropped. Errors go to `onError` (the polling goes on).
 */
export function usePolling<T>(
  task: () => Promise<T>,
  intervalMs: number,
  onResult: (result: T) => void,
  onError?: (error: unknown) => void,
): void {
  // the callbacks are kept in refs so that only `task` and `intervalMs` restart the polling
  const onResultRef = React.useRef(onResult);
  const onErrorRef = React.useRef(onError);
  React.useEffect(() => {
    onResultRef.current = onResult;
    onErrorRef.current = onError;
  });

  React.useEffect(() => {
    let cancelled = false;
    let running = false;

    const round = async () => {
      if (running) return;
      running = true;
      try {
        const result = await task();
        if (!cancelled) onResultRef.current(result);
      } catch (error) {
        if (!cancelled) onErrorRef.current?.(error);
      } finally {
        running = false;
      }
    };

    round();
    const timer = window.setInterval(round, intervalMs);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [task, intervalMs]);
}
