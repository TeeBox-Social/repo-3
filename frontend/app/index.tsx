import { View, ActivityIndicator, StyleSheet } from 'react-native';
import { colors } from '@/src/theme';

export default function Index() {
  return (
    <View style={styles.container}>
      <ActivityIndicator size="large" color={colors.brandPrimary} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface, alignItems: 'center', justifyContent: 'center' },
});
