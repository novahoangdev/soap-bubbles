import * as Haptics from "expo-haptics";

export type HapticKind = "select" | "light" | "medium" | "heavy" | "success" | "error";

/** minimum gap between two haptics of the same kind (ms): a hard puff sprays ~24 bubbles/s */
const GAP: Record<HapticKind, number> = { select: 60, light: 45, medium: 60, heavy: 120, success: 300, error: 300 };
const last: Partial<Record<HapticKind, number>> = {};

/** Called from worklets via scheduleOnRN. */
export const fireHaptic = (kind: HapticKind) => {
  const now = Date.now();
  if (now - (last[kind] ?? 0) < GAP[kind]) return;
  last[kind] = now;
  const p =
    kind === "select"
      ? Haptics.selectionAsync()
      : kind === "success"
        ? Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success)
        : kind === "error"
          ? Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error)
          : Haptics.impactAsync(
              kind === "light"
                ? Haptics.ImpactFeedbackStyle.Light
                : kind === "medium"
                  ? Haptics.ImpactFeedbackStyle.Medium
                  : Haptics.ImpactFeedbackStyle.Heavy,
            );
  p.catch(() => {});
};
