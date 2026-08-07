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
    // KEEP worklets plugin before reanimated's plugin (react-native-reanimated/plugin)
    plugins: [
      'react-native-worklets/plugin',
      'react-native-reanimated/plugin' // must be LAST
    ],
  };
};