/**
 * Wraps repeated polls so only the newest one's answer is shown: an older poll that
 * answers late is dropped instead of overwriting newer results.
 */
export function latestOnly<T>(apply: (value: T) => void) {
  let newest = 0;
  return async (poll: Promise<T>) => {
    const mine = ++newest;
    const value = await poll;
    if (mine === newest) apply(value);
  };
}
