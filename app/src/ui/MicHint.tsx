import React from "react";
import { StyleSheet } from "react-native";
import Animated, { useAnimatedReaction, useAnimatedStyle, useSharedValue, withDelay, withTiming, type SharedValue } from "react-native-reanimated";

/**
 * First-run hint above the wand: "blow gently". Fades in after a moment and fades out for good once a real breath
 * (or a hold on the wand) has been detected. Not shown in demo recordings.
 */
export function MicHint({
  breath,
  top,
  lines = ["blow gently", "into the mic · or hold the wand", "tap the sun to let it set"],
}: {
  breath: SharedValue<number>;
  top: number;
  lines?: [string, string, string];
}) {
  const seen = useSharedValue(false);
  useAnimatedReaction(
    () => breath.value > 0.15,
    (on) => {
      if (on) seen.value = true;
    },
  );
  const style = useAnimatedStyle(() => ({
    opacity: seen.value ? withTiming(0, { duration: 600 }) : withDelay(1200, withTiming(0.85, { duration: 900 })),
    transform: [{ translateY: seen.value ? withTiming(-12, { duration: 600 }) : 0 }],
  }));
  return (
    <Animated.View pointerEvents="none" style={[styles.wrap, { top }, style]}>
      <Animated.Text style={styles.title}>{lines[0]}</Animated.Text>
      <Animated.Text style={styles.sub}>{lines[1]}</Animated.Text>
      <Animated.Text style={styles.sub2}>{lines[2]}</Animated.Text>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  wrap: { position: "absolute", left: 0, right: 0, alignItems: "center" },
  title: {
    color: "#fff6e8",
    fontSize: 22,
    fontWeight: "300",
    letterSpacing: 1.5,
    textShadowColor: "rgba(0,0,0,0.45)",
    textShadowRadius: 8,
  },
  sub2: { color: "rgba(255,246,232,0.5)", fontSize: 11, marginTop: 10, letterSpacing: 0.5, textShadowColor: "rgba(0,0,0,0.45)", textShadowRadius: 6 },
  sub: { color: "rgba(255,246,232,0.7)", fontSize: 13, marginTop: 4, letterSpacing: 0.5, textShadowColor: "rgba(0,0,0,0.45)", textShadowRadius: 6 },
});
