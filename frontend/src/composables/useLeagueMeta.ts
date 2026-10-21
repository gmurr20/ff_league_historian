import { ref, computed } from 'vue';
import type { MetaResponse, SeasonMeta, ManagerMeta } from '@/types/api';
import { fetchMeta } from '@/api/client';

// Singleton state held in module scope
const meta = ref<MetaResponse | null>(null);
const selectedSeason = ref<number | null>(null);
const loading = ref<boolean>(false);
const error = ref<string | null>(null);
const initialized = ref<boolean>(false);

export function useLeagueMeta() {
  const availableSeasons = computed<SeasonMeta[]>(() => {
    return meta.value?.available_seasons ?? [];
  });

  const currentSeasonMeta = computed<SeasonMeta | null>(() => {
    if (!meta.value || !meta.value.available_seasons) return null;
    if (selectedSeason.value != null) {
      return meta.value.available_seasons.find(s => s.season_year === selectedSeason.value) || null;
    }
    return (
      meta.value.available_seasons.find(s => s.is_active) ||
      meta.value.available_seasons[0] ||
      null
    );
  });

  const managers = computed<ManagerMeta[]>(() => {
    return meta.value?.managers ?? [];
  });

  async function loadMeta(force = false): Promise<void> {
    if (initialized.value && !force && meta.value) return;

    loading.value = true;
    error.value = null;
    try {
      const data = await fetchMeta();
      meta.value = data;
      // Default selected season to current_season or latest available season
      if (selectedSeason.value === null) {
        if (data.current_season) {
          selectedSeason.value = data.current_season;
        } else if (data.available_seasons && data.available_seasons.length > 0) {
          selectedSeason.value = data.available_seasons[0].season_year;
        }
      }
      initialized.value = true;
    } catch (err: unknown) {
      if (err instanceof Error) {
        error.value = err.message;
      } else {
        error.value = 'Failed to load league metadata';
      }
      console.error('Error loading league metadata:', err);
    } finally {
      loading.value = false;
    }
  }

  function setSelectedSeason(year: number | null): void {
    selectedSeason.value = year;
  }

  return {
    meta,
    selectedSeason,
    availableSeasons,
    currentSeasonMeta,
    managers,
    loading,
    error,
    loadMeta,
    setSelectedSeason,
  };
}
