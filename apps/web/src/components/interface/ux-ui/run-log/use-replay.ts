"use client";

/**
 * Replaying a captured run on its own clock.
 *
 * The console's live feel comes from steps arriving one at a time with a pause
 * between them, and a design cannot be judged on a list that appears all at
 * once — the thing being designed is partly the arrival. So this replays a run
 * the console really performed, using the gaps the run really had: 3s to be
 * claimed, 43s parked on the operator, 20s of web searches, 1s to open the pull
 * request.
 *
 * Compressed, because 5m 35s of real time is not a demo. The compression is
 * uniform, so the shape of the run survives: the hold is still by far the
 * longest pause, and the two sub-second bursts still read as bursts.
 *
 * No network, no timers on the server, no shared state. Remounting starts over,
 * which is what a refresh should do to a replay.
 */

import { useCallback, useEffect, useRef, useState } from "react";

/** Real seconds per replayed second. The run's own gaps, divided by this. */
export const DEFAULT_SPEED = 12;

/** No single gap is allowed to stall the replay longer than this. */
const MAX_GAP_MS = 1400;

/** How often the clock advances. Fast enough that durations tick smoothly. */
const FRAME_MS = 50;

export interface Replay {
  /** Milliseconds of run time elapsed. Compare against a step's `at`. */
  elapsed: number;
  playing: boolean;
  done: boolean;
  speed: number;
  /** 0 to 1, for a progress bar. */
  progress: number;
  play: () => void;
  pause: () => void;
  restart: () => void;
  setSpeed: (speed: number) => void;
  /** Jump to the end and stop, for looking at the finished shape. */
  skip: () => void;
}

/**
 * Advance a clock over a run of `totalMs`, pausing at each moment in `beats`.
 *
 * `beats` are the `at` values of the steps. Between two beats the clock runs at
 * `speed`, but a gap longer than `MAX_GAP_MS` of wall time is cut short: the
 * operator hold should read as the longest wait in the run without actually
 * making anyone wait through it.
 */
export function useReplay(totalMs: number, beats: number[], initialSpeed = DEFAULT_SPEED): Replay {
  const [elapsed, setElapsed] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [speed, setSpeed] = useState(initialSpeed);

  // Held in a ref so a new beat list does not tear down the running interval.
  // Written in an effect rather than during render: the interval only reads it
  // on its next tick, which is always after the effect has run.
  const marks = useRef(beats);
  useEffect(() => {
    marks.current = beats;
  }, [beats]);

  useEffect(() => {
    if (!playing) return;
    const timer = window.setInterval(() => {
      setElapsed((was) => {
        const step = FRAME_MS * speed;
        let next = was + step;
        // The next moment something happens. Long dead air before it is skipped
        // down to a beat the eye can still read as a pause.
        const upcoming = marks.current.find((mark) => mark > was);
        if (upcoming !== undefined && upcoming > next && (upcoming - was) / speed > MAX_GAP_MS) {
          next = upcoming;
        }
        if (next >= totalMs) {
          // Stopping here rather than in an effect on `done`: the clock is the
          // external system, so the tick that reaches the end is the right place
          // to stop it, and it saves a cascading render.
          setPlaying(false);
          return totalMs;
        }
        return next;
      });
    }, FRAME_MS);
    return () => window.clearInterval(timer);
  }, [playing, speed, totalMs]);

  const done = elapsed >= totalMs;

  const restart = useCallback(() => {
    setElapsed(0);
    setPlaying(true);
  }, []);

  const skip = useCallback(() => {
    setElapsed(totalMs);
    setPlaying(false);
  }, [totalMs]);

  return {
    elapsed,
    playing,
    done,
    speed,
    progress: totalMs === 0 ? 1 : Math.min(1, elapsed / totalMs),
    play: useCallback(() => setPlaying(true), []),
    pause: useCallback(() => setPlaying(false), []),
    restart,
    setSpeed,
    skip,
  };
}
