# ProGuard rules for Android native libraries used by the app
# Keep Reanimated runtime classes and JNI-related classes
-keep class com.swmansion.reanimated.** { *; }
-keep class com.facebook.jni.** { *; }

# Keep annotation attributes
-keepattributes *Annotation*

# Keep classes and methods used via reflection or JavaScript interfaces
-keepclassmembers class * {
  @android.webkit.JavascriptInterface <methods>;
}

# Add additional keep rules as needed for other native SDKs (Firebase, etc.)