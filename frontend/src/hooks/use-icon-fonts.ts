// Icon font loader for Expo apps. Fonts are loaded from a CDN only under
// Expo Go (StoreClient) — that's where @expo/vector-icons' .ttf files come
// back as 0 bytes from Metro's asset resolver on Android. Native dev/prod
// builds and web pass an empty map, so useFonts resolves to [true, null]
// immediately via react-native-vector-icons autolinking / web stubs.
// ICON_VECTOR_VERSION must match @expo/vector-icons in package.json.
// Usage: const [loaded, error] = useIconFonts();

import { useFonts } from "expo-font";
import Ionicons from "@expo/vector-icons/Ionicons";

// Ionicons is the ONLY @expo/vector-icons family the app renders, so we only
// need to preload that one font. `Ionicons.font` is the library's own static
// font map ({ ionicons: <bundled .ttf> }) — this is the Expo-documented,
// reliable way to preload icon fonts and works in Expo Go, dev builds and
// production alike.
//
// This replaces a previous runtime-CDN loader that fetched every icon family
// from jsDelivr. That approach was fragile on real devices / published builds
// (it depended on live network access to a CDN at cold start) and, combined
// with the tree rendering before the fonts registered, caused the Expo Go
// blank / stuck-on-splash symptom.
export const useIconFonts = (): readonly [boolean, Error | null] =>
  useFonts(Ionicons.font);
