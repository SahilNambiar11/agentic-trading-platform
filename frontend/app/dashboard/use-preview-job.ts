"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  enqueueStrategyPreview,
  getPreviewJob,
  StrategyApiError,
} from "@/lib/strategies/api";
import type { PreviewJob, StrategyPreview } from "@/lib/strategies/types";

const POLL_INTERVAL_MS = 1_000;

function getErrorMessage(error: unknown): string {
  if (error instanceof DOMException && error.name === "AbortError") {
    return "";
  }
  return error instanceof StrategyApiError
    ? error.message
    : "Unable to check the preview job. Please try again.";
}

function queuedJob(jobId: string): PreviewJob {
  return {
    id: jobId,
    status: "queued",
    stage: "queued",
    progress: 5,
    created_at: new Date().toISOString(),
    started_at: null,
    completed_at: null,
    error: null,
    preview_result: null,
  };
}

export type PreviewJobPolling = {
  job: PreviewJob | null;
  preview: StrategyPreview | null;
  error: string | null;
  isSubmitting: boolean;
  isActive: boolean;
  submit: (strategyText: string) => Promise<boolean>;
  reset: () => void;
};

export function usePreviewJob(): PreviewJobPolling {
  const [job, setJob] = useState<PreviewJob | null>(null);
  const [preview, setPreview] = useState<StrategyPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const generationRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const requestRef = useRef<AbortController | null>(null);

  const stopCurrentRequest = useCallback(() => {
    generationRef.current += 1;
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    requestRef.current?.abort();
    requestRef.current = null;
  }, []);

  const reset = useCallback(() => {
    stopCurrentRequest();
    setJob(null);
    setPreview(null);
    setError(null);
    setIsSubmitting(false);
  }, [stopCurrentRequest]);

  const pollRef = useRef<(jobId: string, generation: number) => Promise<void>>(
    async () => undefined,
  );

  const poll = useCallback(async (jobId: string, generation: number) => {
    if (generation !== generationRef.current) {
      return;
    }

    const controller = new AbortController();
    requestRef.current = controller;

    try {
      const nextJob = await getPreviewJob(jobId, controller.signal);
      if (generation !== generationRef.current) {
        return;
      }

      setJob(nextJob);
      setError(null);
      if (nextJob.status === "completed") {
        setPreview(nextJob.preview_result);
        requestRef.current = null;
        return;
      }
      if (nextJob.status === "failed") {
        setError(nextJob.error ?? "Unable to complete the strategy preview.");
        requestRef.current = null;
        return;
      }
    } catch (pollError) {
      if (generation !== generationRef.current || controller.signal.aborted) {
        return;
      }
      setError(getErrorMessage(pollError));
    }

    if (generation === generationRef.current) {
      requestRef.current = null;
      timerRef.current = setTimeout(() => {
        timerRef.current = null;
        void pollRef.current(jobId, generation);
      }, POLL_INTERVAL_MS);
    }
  }, []);

  useEffect(() => {
    pollRef.current = poll;
  }, [poll]);

  const submit = useCallback(
    async (strategyText: string): Promise<boolean> => {
      stopCurrentRequest();
      const generation = generationRef.current;
      const controller = new AbortController();
      requestRef.current = controller;
      setJob(null);
      setPreview(null);
      setError(null);
      setIsSubmitting(true);

      try {
        const result = await enqueueStrategyPreview(strategyText, controller.signal);
        if (generation !== generationRef.current) {
          return false;
        }

        setJob(queuedJob(result.job_id));
        setIsSubmitting(false);
        requestRef.current = null;
        void pollRef.current(result.job_id, generation);
        return true;
      } catch (submissionError) {
        if (generation !== generationRef.current || controller.signal.aborted) {
          return false;
        }
        setError(getErrorMessage(submissionError));
        setIsSubmitting(false);
        requestRef.current = null;
        return false;
      }
    },
    [stopCurrentRequest],
  );

  useEffect(
    () => () => {
      stopCurrentRequest();
    },
    [stopCurrentRequest],
  );

  return {
    job,
    preview,
    error,
    isSubmitting,
    isActive:
      isSubmitting || job?.status === "queued" || job?.status === "running",
    submit,
    reset,
  };
}
