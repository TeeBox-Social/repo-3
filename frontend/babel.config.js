module.exports = function (api) {
  api.cache(true);
  return {
    presets: ['babel-preset-expo'],
    // react-native-worklets/plugin transforms worklet functions used by
    // react-native-reanimated 4 (pulled in by expo-router and
    // react-native-keyboard-controller). Without an explicit babel.config.js
    // the plugin is NOT applied in EAS standalone release builds, so worklet
    // initialisation crashes the app at launch on the New Architecture (while
    // Expo Go / web dev mask the issue).
    //
    // NOTE: In Reanimated 4, `react-native-reanimated/plugin` is just a
    // re-export of `react-native-worklets/plugin`, so we register ONLY the
    // worklets plugin here — adding both would run the same transform twice
    // and break the build. This MUST remain the last plugin.
    plugins: ['react-native-worklets/plugin'],
  };
};