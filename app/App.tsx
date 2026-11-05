import { useState } from "react";
import { StatusBar } from "expo-status-bar";
import { Pressable, StyleSheet, Text } from "react-native";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { BubbleScene } from "./src/scene/BubbleScene";
import { Garden3D } from "./src/garden3d/Garden3D";

/** two modes: the photoreal 2D bubbles (Skia) and the 3D garden (three.js); EXPO_PUBLIC_MODE=3d starts in the garden */
export default function App() {
  const [mode, setMode] = useState<"2d" | "3d">(process.env.EXPO_PUBLIC_MODE === "3d" ? "3d" : "2d");
  return (
    <GestureHandlerRootView style={{ flex: 1, backgroundColor: "#120c08" }}>
      <StatusBar hidden />
      {mode === "2d" ? (
        <>
          <BubbleScene />
          {process.env.EXPO_PUBLIC_DEMO !== "1" && (
            <Pressable style={styles.btn} onPress={() => setMode("3d")} hitSlop={12}>
              <Text style={styles.txt}>3D</Text>
            </Pressable>
          )}
        </>
      ) : (
        <Garden3D onExit={process.env.EXPO_PUBLIC_DEMO3D === "1" ? undefined : () => setMode("2d")} />
      )}
    </GestureHandlerRootView>
  );
}

const styles = StyleSheet.create({
  btn: { position: "absolute", top: 58, left: 18, paddingHorizontal: 12, paddingVertical: 6, borderRadius: 14, backgroundColor: "rgba(255,255,255,0.18)" },
  txt: { color: "#f4ead8", fontWeight: "600", fontSize: 13 },
});
