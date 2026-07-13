let active: HTMLAudioElement | null = null;

export function claim(audio: HTMLAudioElement): void {
  if (active && active !== audio) active.pause();
  active = audio;
}

export function release(audio: HTMLAudioElement): void {
  if (active === audio) active = null;
}
