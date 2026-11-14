import { describe, expect, it } from "vitest";
import { latestOnly } from "./latest";

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

describe("latestOnly", () => {
  it("keeps the newest poll's answer when an older poll answers after it", async () => {
    const shown: string[] = [];
    const track = latestOnly<string>((value) => shown.push(value));
    const older = deferred<string>();
    const newer = deferred<string>();

    const a = track(older.promise);
    const b = track(newer.promise);
    newer.resolve("50% within 5 m");
    await b;
    older.resolve("0% within 5 m");
    await a;

    expect(shown).toEqual(["50% within 5 m"]);
  });

  it("shows each answer when polls answer in order", async () => {
    const shown: number[] = [];
    const track = latestOnly<number>((value) => shown.push(value));

    await track(Promise.resolve(1));
    await track(Promise.resolve(2));

    expect(shown).toEqual([1, 2]);
  });
});
