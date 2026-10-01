"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { errorMessage } from "./api";

export interface AsyncState<T> {
  data: T | undefined;
  error: string | undefined;
  /** HTTP status of the failure, when there is one (e.g. 404 vs 403). */
  status: number | undefined;
  loading: boolean;
  reload: () => void;
}

/** Load once (and on `reload`). `poll` re-runs it every N ms while `shouldPoll(data)` holds. */
export function useAsync<T>(
  fn: () => Promise<T>,
  deps: unknown[],
  poll?: { everyMs: number; shouldPoll: (data: T | undefined) => boolean },
): AsyncState<T> {
  const [data, setData] = useState<T>();
  const [error, setError] = useState<string>();
  const [status, setStatus] = useState<number>();
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  const fnRef = useRef(fn);
  fnRef.current = fn;

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const run = async (first: boolean) => {
      if (first) setLoading(true);
      try {
        const result = await fnRef.current();
        if (cancelled) return;
        setData(result);
        setError(undefined);
        setStatus(undefined);
        if (poll?.shouldPoll(result)) timer = setTimeout(() => run(false), poll.everyMs);
      } catch (e) {
        if (cancelled) return;
        setError(errorMessage(e));
        setStatus((e as { status?: number }).status);
      } finally {
        if (!cancelled && first) setLoading(false);
      }
    };
    void run(true);
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [...deps, tick]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { data, error, status, loading, reload };
}
