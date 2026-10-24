<script setup lang="ts">
import { ref, computed, watch, onUnmounted } from 'vue';
import type { TopTradePartner, TradeDetail, TradePlayerAsset, SeasonMeta } from '@/types/api';
import TradePartnerAllianceCard from '@/components/trades/TradePartnerAllianceCard.vue';
import TradeAutopsyCard from '@/components/trades/TradeAutopsyCard.vue';
import TeamAvatar from '@/components/ui/TeamAvatar.vue';
import {
  ArrowLeftRight,
  ArrowRight,
  RotateCcw,
  Info,
  Play,
  Pause,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  ExternalLink,
} from 'lucide-vue-next';
import { positionTextClass } from '@/components/trades/tradeUi';
import { useLeagueMeta } from '@/composables/useLeagueMeta';

interface ManagerNode {
  id: number;
  name: string;
  teamName: string;
  avatarUrl: string | null;
  totalTrades: number;
  totalAssetsMoved: number;
  totalScoreVolume: number;
  partnerIds: Set<number>;
  x: number;
  y: number;
  isActive: boolean;
}

interface GraphEdge {
  key: string;
  partner?: TopTradePartner;
  source: ManagerNode;
  target: ManagerNode;
  pathD: string;
  midX: number;
  midY: number;
  strokeWidth: number;
  tradeCount: number;
  volume: number;
}

interface FlowItem {
  id: string;
  name: string;
  fullName: string;
  position: string;
  proTeam: string;
  headshotUrl: string | null;
  isFaab: boolean;
  isPick: boolean;
  score: number;
  fromTeamName: string;
  toTeamName: string;
  direction: 'A_TO_B' | 'B_TO_A';
  style: Record<string, string>;
}

const props = withDefaults(
  defineProps<{
    partners: TopTradePartner[];
    trades: TradeDetail[];
    seasonLabel?: string;
    isAllTime?: boolean;
    seasonYear?: number | null;
    availableSeasons?: SeasonMeta[];
  }>(),
  {
    seasonLabel: 'All-Time Career',
    isAllTime: undefined,
    seasonYear: null,
    availableSeasons: () => [],
  }
);

const emit = defineEmits<{
  (e: 'select-trade', trade: TradeDetail): void;
}>();

// Mobile view mode toggle: 'duel' (interactive card flow) vs 'graph' (interactive SVG network)
const mobileViewMode = ref<'duel' | 'graph'>('duel');

// Determine if we are rendering All-Time cumulative graph vs single season chronological flow
const isAllTimeView = computed<boolean>(() => {
  if (props.isAllTime !== undefined) return props.isAllTime;
  return props.seasonLabel.toLowerCase().includes('all-time') || props.seasonYear === null;
});

const { managers } = useLeagueMeta();

const activeManagerMap = computed<Map<number, boolean>>(() => {
  const map = new Map<number, boolean>();
  for (const m of managers.value) {
    map.set(m.id, m.is_active);
  }
  return map;
});

function isManagerActive(id: number): boolean {
  return activeManagerMap.value.get(id) ?? true;
}

// Selection state for isolating specific corridors in the ledger below
const selectedManagerId = ref<number | null>(null);
const selectedAllianceKey = ref<string | null>(null);
const hoveredEdgeKey = ref<string | null>(null);
const hoveredNodeId = ref<number | null>(null);

// Playback state
const currentTradeIndex = ref<number>(0);
const isPlaying = ref<boolean>(false);
const tradeProgress = ref<number>(0); // 0 to 100 percentage
const playbackSpeed = ref<'slow' | 'normal' | 'fast'>('slow');
const animKey = ref<number>(0);
const failedHeadshots = ref<Record<string, boolean>>({});

// Deterministic timer state
let playbackTimeout: ReturnType<typeof setTimeout> | null = null;
let progressInterval: ReturnType<typeof setInterval> | null = null;
let stepStartTime = 0;

// Speed tuning
const speedSettings = computed(() => {
  switch (playbackSpeed.value) {
    case 'fast':
      return { stepMs: 2500, flightSec: 1.6, staggerSec: 0.2, entranceSec: 0.15 };
    case 'normal':
      return { stepMs: 3800, flightSec: 2.4, staggerSec: 0.3, entranceSec: 0.25 };
    case 'slow':
    default:
      return { stepMs: 5200, flightSec: 3.2, staggerSec: 0.4, entranceSec: 0.3 };
  }
});

function makeAllianceKey(a: number, b: number): string {
  return a < b ? `${a}-${b}` : `${b}-${a}`;
}

function handleHeadshotError(key: string) {
  failedHeadshots.value[key] = true;
}

function formatPlayerName(fullName: string): string {
  if (!fullName) return '';
  if (fullName.length <= 16) return fullName;
  const parts = fullName.trim().split(/\s+/);
  if (parts.length >= 2) {
    return `${parts[0][0]}. ${parts.slice(1).join(' ')}`;
  }
  return fullName;
}

function getAssetDisplayName(asset: TradePlayerAsset): string {
  if (asset.asset_type === 'PICK') {
    const pickLabel = `Pick ${asset.pick_round ?? '?'}.${String(asset.pick_number ?? 0).padStart(2, '0')}`;
    return asset.drafted_player_name ? `${pickLabel} (${formatPlayerName(asset.drafted_player_name)})` : pickLabel;
  }
  return formatPlayerName(asset.full_name);
}

// Exact trade counts per bilateral pair from the trades dataset
const pairTradeCounts = computed(() => {
  const counts = new Map<string, number>();
  for (const t of props.trades) {
    if (t.sides.length >= 2) {
      const key = makeAllianceKey(t.sides[0].manager_id, t.sides[1].manager_id);
      counts.set(key, (counts.get(key) || 0) + 1);
    }
  }
  return counts;
});

// Chronological sorting of all trades for that year
const chronologicalTrades = computed<TradeDetail[]>(() => {
  return [...props.trades].sort((a, b) => {
    if (a.season_year !== b.season_year) {
      return a.season_year - b.season_year;
    }
    const weekA = a.week ?? 0;
    const weekB = b.week ?? 0;
    if (weekA !== weekB) {
      return weekA - weekB;
    }
    if (a.executed_at && b.executed_at) {
      return new Date(a.executed_at).getTime() - new Date(b.executed_at).getTime();
    }
    return a.trade_id - b.trade_id;
  });
});

const playbackTrades = computed<TradeDetail[]>(() => {
  return chronologicalTrades.value;
});

// Currently active trade in the playback theater
const activeTrade = computed<TradeDetail | null>(() => {
  if (playbackTrades.value.length === 0) return null;
  return playbackTrades.value[currentTradeIndex.value] ?? playbackTrades.value[0] ?? null;
});

const activeSideA = computed(() => activeTrade.value?.sides[0] ?? null);
const activeSideB = computed(() => activeTrade.value?.sides[1] ?? null);

watch(playbackTrades, (newTrades) => {
  if (currentTradeIndex.value >= newTrades.length) {
    currentTradeIndex.value = Math.max(0, newTrades.length - 1);
  }
  tradeProgress.value = 0;
  animKey.value++;
});

watch(currentTradeIndex, () => {
  tradeProgress.value = 0;
  animKey.value++;
});

function clearTimers() {
  if (playbackTimeout) {
    clearTimeout(playbackTimeout);
    playbackTimeout = null;
  }
  if (progressInterval) {
    clearInterval(progressInterval);
    progressInterval = null;
  }
}

function scheduleStep() {
  clearTimers();
  if (!isPlaying.value || playbackTrades.value.length === 0) return;

  stepStartTime = Date.now();
  tradeProgress.value = 0;

  progressInterval = setInterval(() => {
    if (!isPlaying.value) {
      clearTimers();
      return;
    }
    const elapsed = Date.now() - stepStartTime;
    const total = speedSettings.value.stepMs;
    tradeProgress.value = Math.min(100, Math.round((elapsed / total) * 100));
  }, 30);

  playbackTimeout = setTimeout(() => {
    if (!isPlaying.value) return;

    if (currentTradeIndex.value < playbackTrades.value.length - 1) {
      currentTradeIndex.value++;
    } else {
      currentTradeIndex.value = 0;
    }

    scheduleStep();
  }, speedSettings.value.stepMs);
}

function play() {
  if (playbackTrades.value.length === 0) return;
  isPlaying.value = true;
  scheduleStep();
}

function pause() {
  isPlaying.value = false;
  clearTimers();
}

function togglePlay() {
  if (isPlaying.value) {
    pause();
  } else {
    play();
  }
}

function setSpeed(newSpeed: 'slow' | 'normal' | 'fast') {
  playbackSpeed.value = newSpeed;
  if (isPlaying.value) {
    scheduleStep();
  }
}

function prevTrade() {
  if (currentTradeIndex.value > 0) {
    goToTrade(currentTradeIndex.value - 1);
  } else {
    goToTrade(playbackTrades.value.length - 1);
  }
}

function nextTrade() {
  if (currentTradeIndex.value < playbackTrades.value.length - 1) {
    goToTrade(currentTradeIndex.value + 1);
  } else {
    goToTrade(0);
  }
}

function goToTrade(index: number) {
  if (index >= 0 && index < playbackTrades.value.length) {
    currentTradeIndex.value = index;
    tradeProgress.value = 0;
    if (isPlaying.value) {
      scheduleStep();
    }
  }
}

function resetPlayback() {
  pause();
  currentTradeIndex.value = 0;
  tradeProgress.value = 0;
}

onUnmounted(() => {
  clearTimers();
});

// Canvas dimensions for layout
const canvasWidth = 960;
const canvasHeight = 580;
const centerX = 480;
const centerY = 285;

const graphData = computed(() => {
  const nodeMap = new Map<number, ManagerNode>();

  for (const p of props.partners) {
    if (!nodeMap.has(p.manager_a_id)) {
      nodeMap.set(p.manager_a_id, {
        id: p.manager_a_id,
        name: p.manager_a_name,
        teamName: p.manager_a_team_name,
        avatarUrl: p.manager_a_avatar_url,
        totalTrades: 0,
        totalAssetsMoved: 0,
        totalScoreVolume: 0,
        partnerIds: new Set<number>(),
        x: centerX,
        y: centerY,
        isActive: isManagerActive(p.manager_a_id),
      });
    }
    const nodeA = nodeMap.get(p.manager_a_id)!;
    nodeA.totalTrades += p.trade_count;
    nodeA.totalAssetsMoved += p.total_assets_exchanged;
    nodeA.totalScoreVolume += p.total_trade_score_volume;
    nodeA.partnerIds.add(p.manager_b_id);

    if (!nodeMap.has(p.manager_b_id)) {
      nodeMap.set(p.manager_b_id, {
        id: p.manager_b_id,
        name: p.manager_b_name,
        teamName: p.manager_b_team_name,
        avatarUrl: p.manager_b_avatar_url,
        totalTrades: 0,
        totalAssetsMoved: 0,
        totalScoreVolume: 0,
        partnerIds: new Set<number>(),
        x: centerX,
        y: centerY,
        isActive: isManagerActive(p.manager_b_id),
      });
    }
    const nodeB = nodeMap.get(p.manager_b_id)!;
    nodeB.totalTrades += p.trade_count;
    nodeB.totalAssetsMoved += p.total_assets_exchanged;
    nodeB.totalScoreVolume += p.total_trade_score_volume;
    nodeB.partnerIds.add(p.manager_a_id);
  }

  for (const t of props.trades) {
    if (t.sides.length >= 2) {
      const s0 = t.sides[0];
      const s1 = t.sides[1];
      if (!nodeMap.has(s0.manager_id)) {
        nodeMap.set(s0.manager_id, {
          id: s0.manager_id,
          name: s0.manager_name,
          teamName: s0.team_name,
          avatarUrl: s0.logo_url,
          totalTrades: 0,
          totalAssetsMoved: 0,
          totalScoreVolume: 0,
          partnerIds: new Set<number>(),
          x: centerX,
          y: centerY,
          isActive: isManagerActive(s0.manager_id),
        });
      }
      if (!nodeMap.has(s1.manager_id)) {
        nodeMap.set(s1.manager_id, {
          id: s1.manager_id,
          name: s1.manager_name,
          teamName: s1.team_name,
          avatarUrl: s1.logo_url,
          totalTrades: 0,
          totalAssetsMoved: 0,
          totalScoreVolume: 0,
          partnerIds: new Set<number>(),
          x: centerX,
          y: centerY,
          isActive: isManagerActive(s1.manager_id),
        });
      }
      const n0 = nodeMap.get(s0.manager_id)!;
      const n1 = nodeMap.get(s1.manager_id)!;
      n0.partnerIds.add(s1.manager_id);
      n1.partnerIds.add(s0.manager_id);
      n0.totalTrades = Math.max(n0.totalTrades, 1);
      n1.totalTrades = Math.max(n1.totalTrades, 1);
    }
  }

  const nodes = Array.from(nodeMap.values());
  const N = nodes.length;

  if (N === 0) {
    return { nodes: [], edges: [], nodeMap };
  }

  if (N === 1) {
    nodes[0].x = centerX;
    nodes[0].y = centerY;
  } else if (N === 2) {
    nodes[0].x = centerX - 220;
    nodes[0].y = centerY;
    nodes[1].x = centerX + 220;
    nodes[1].y = centerY;
  } else {
    const radiusX = Math.min(330, Math.max(230, 340 - (N > 12 ? (N - 12) * 5 : 0)));
    const radiusY = Math.min(170, Math.max(130, 175 - (N > 12 ? (N - 12) * 4 : 0)));

    nodes.forEach((node, i) => {
      const theta = -Math.PI / 2 + (2 * Math.PI * i) / N;
      node.x = Math.round(centerX + radiusX * Math.cos(theta));
      node.y = Math.round(centerY + radiusY * Math.sin(theta));
    });
  }

  const edgeMap = new Map<string, GraphEdge>();

  for (const p of props.partners) {
    const s = nodeMap.get(p.manager_a_id);
    const t = nodeMap.get(p.manager_b_id);
    if (!s || !t) continue;

    const key = makeAllianceKey(p.manager_a_id, p.manager_b_id);
    const actualCount = pairTradeCounts.value.get(key) ?? p.trade_count ?? 1;
    const midX = Math.round((s.x + t.x) / 2);
    const midY = Math.round((s.y + t.y) / 2);
    const pathD = `M ${s.x} ${s.y} L ${t.x} ${t.y}`;
    const strokeWidth = Math.min(10, Math.max(2.5, 1.5 + actualCount * 2));

    edgeMap.set(key, {
      key,
      partner: p,
      source: s,
      target: t,
      pathD,
      midX,
      midY,
      strokeWidth,
      tradeCount: actualCount,
      volume: p.total_trade_score_volume,
    });
  }

  for (const tr of props.trades) {
    if (tr.sides.length < 2) continue;
    const sA = nodeMap.get(tr.sides[0].manager_id);
    const sB = nodeMap.get(tr.sides[1].manager_id);
    if (!sA || !sB) continue;

    const key = makeAllianceKey(sA.id, sB.id);
    const actualCount = pairTradeCounts.value.get(key) ?? 1;

    if (!edgeMap.has(key)) {
      const midX = Math.round((sA.x + sB.x) / 2);
      const midY = Math.round((sA.y + sB.y) / 2);
      const pathD = `M ${sA.x} ${sA.y} L ${sB.x} ${sB.y}`;
      const strokeWidth = Math.min(10, Math.max(2.5, 1.5 + actualCount * 2));

      edgeMap.set(key, {
        key,
        source: sA,
        target: sB,
        pathD,
        midX,
        midY,
        strokeWidth,
        tradeCount: actualCount,
        volume: tr.sides[0].total_trade_score + tr.sides[1].total_trade_score,
      });
    }
  }

  const edges = Array.from(edgeMap.values());
  return { nodes, edges, nodeMap };
});

const activeNodeA = computed<ManagerNode | null>(() => {
  if (!isPlaying.value || isAllTimeView.value || !activeSideA.value) return null;
  return graphData.value.nodeMap.get(activeSideA.value.manager_id) ?? null;
});

const activeNodeB = computed<ManagerNode | null>(() => {
  if (!isPlaying.value || isAllTimeView.value || !activeSideB.value) return null;
  return graphData.value.nodeMap.get(activeSideB.value.manager_id) ?? null;
});

const activeEdgeKey = computed<string | null>(() => {
  if (!isPlaying.value || isAllTimeView.value || !activeNodeA.value || !activeNodeB.value) return null;
  return makeAllianceKey(activeNodeA.value.id, activeNodeB.value.id);
});

// Floating player tokens (for single season animated replay)
const activeFlowItems = computed<FlowItem[]>(() => {
  if (!isPlaying.value || isAllTimeView.value) return [];
  if (!activeTrade.value || !activeSideA.value || !activeSideB.value) return [];
  const nA = activeNodeA.value;
  const nB = activeNodeB.value;
  if (!nA || !nB) return [];

  const items: FlowItem[] = [];
  const sA = activeSideA.value;
  const sB = activeSideB.value;

  const dx = nB.x - nA.x;
  const dy = nB.y - nA.y;
  const dist = Math.hypot(dx, dy) || 1;
  const nx = -dy / dist;
  const ny = dx / dist;
  const laneOffset = 26;

  const { flightSec, staggerSec, entranceSec } = speedSettings.value;

  const bToAMidX = (nA.x + nB.x) / 2 + nx * laneOffset;
  const bToAMidY = (nA.y + nB.y) / 2 + ny * laneOffset;

  sA.assets_received.forEach((asset, idx) => {
    const delaySec = entranceSec + idx * staggerSec;
    items.push({
      id: `${activeTrade.value!.trade_id}-b2a-${asset.player_id || idx}`,
      name: getAssetDisplayName(asset),
      fullName: asset.full_name,
      position: asset.default_position || asset.asset_type,
      proTeam: asset.pro_team || 'FA',
      headshotUrl: asset.headshot_url || asset.drafted_player_headshot_url,
      isFaab: false,
      isPick: asset.asset_type === 'PICK',
      score: asset.trade_score,
      fromTeamName: sB.team_name || sB.manager_name,
      toTeamName: sA.team_name || sA.manager_name,
      direction: 'B_TO_A',
      style: {
        '--startX': `${(nB.x / canvasWidth) * 100}%`,
        '--startY': `${(nB.y / canvasHeight) * 100}%`,
        '--midX': `${(bToAMidX / canvasWidth) * 100}%`,
        '--midY': `${(bToAMidY / canvasHeight) * 100}%`,
        '--endX': `${(nA.x / canvasWidth) * 100}%`,
        '--endY': `${(nA.y / canvasHeight) * 100}%`,
        '--duration': `${flightSec}s`,
        '--delay': `${delaySec}s`,
      },
    });
  });

  if (sA.faab_received > 0) {
    const delaySec = entranceSec + sA.assets_received.length * staggerSec;
    items.push({
      id: `${activeTrade.value.trade_id}-b2a-faab`,
      name: `$${sA.faab_received} FAAB`,
      fullName: `$${sA.faab_received} FAAB Budget`,
      position: 'FAAB',
      proTeam: 'FAAB',
      headshotUrl: null,
      isFaab: true,
      isPick: false,
      score: sA.faab_value,
      fromTeamName: sB.team_name || sB.manager_name,
      toTeamName: sA.team_name || sA.manager_name,
      direction: 'B_TO_A',
      style: {
        '--startX': `${(nB.x / canvasWidth) * 100}%`,
        '--startY': `${(nB.y / canvasHeight) * 100}%`,
        '--midX': `${(bToAMidX / canvasWidth) * 100}%`,
        '--midY': `${(bToAMidY / canvasHeight) * 100}%`,
        '--endX': `${(nA.x / canvasWidth) * 100}%`,
        '--endY': `${(nA.y / canvasHeight) * 100}%`,
        '--duration': `${flightSec}s`,
        '--delay': `${delaySec}s`,
      },
    });
  }

  const aToBMidX = (nA.x + nB.x) / 2 - nx * laneOffset;
  const aToBMidY = (nA.y + nB.y) / 2 - ny * laneOffset;

  sB.assets_received.forEach((asset, idx) => {
    const delaySec = entranceSec + (idx + 0.15) * staggerSec;
    items.push({
      id: `${activeTrade.value!.trade_id}-a2b-${asset.player_id || idx}`,
      name: getAssetDisplayName(asset),
      fullName: asset.full_name,
      position: asset.default_position || asset.asset_type,
      proTeam: asset.pro_team || 'FA',
      headshotUrl: asset.headshot_url || asset.drafted_player_headshot_url,
      isFaab: false,
      isPick: asset.asset_type === 'PICK',
      score: asset.trade_score,
      fromTeamName: sA.team_name || sA.manager_name,
      toTeamName: sB.team_name || sB.manager_name,
      direction: 'A_TO_B',
      style: {
        '--startX': `${(nA.x / canvasWidth) * 100}%`,
        '--startY': `${(nA.y / canvasHeight) * 100}%`,
        '--midX': `${(aToBMidX / canvasWidth) * 100}%`,
        '--midY': `${(aToBMidY / canvasHeight) * 100}%`,
        '--endX': `${(nB.x / canvasWidth) * 100}%`,
        '--endY': `${(nB.y / canvasHeight) * 100}%`,
        '--duration': `${flightSec}s`,
        '--delay': `${delaySec}s`,
      },
    });
  });

  if (sB.faab_received > 0) {
    const delaySec = entranceSec + (sB.assets_received.length + 0.15) * staggerSec;
    items.push({
      id: `${activeTrade.value.trade_id}-a2b-faab`,
      name: `$${sB.faab_received} FAAB`,
      fullName: `$${sB.faab_received} FAAB Budget`,
      position: 'FAAB',
      proTeam: 'FAAB',
      headshotUrl: null,
      isFaab: true,
      isPick: false,
      score: sB.faab_value,
      fromTeamName: sA.team_name || sA.manager_name,
      toTeamName: sB.team_name || sB.manager_name,
      direction: 'A_TO_B',
      style: {
        '--startX': `${(nA.x / canvasWidth) * 100}%`,
        '--startY': `${(nA.y / canvasHeight) * 100}%`,
        '--midX': `${(aToBMidX / canvasWidth) * 100}%`,
        '--midY': `${(aToBMidY / canvasHeight) * 100}%`,
        '--endX': `${(nB.x / canvasWidth) * 100}%`,
        '--endY': `${(nB.y / canvasHeight) * 100}%`,
        '--duration': `${flightSec}s`,
        '--delay': `${delaySec}s`,
      },
    });
  }

  return items;
});

function getInitials(name: string): string {
  const words = (name || '').trim().split(/\s+/).filter(Boolean);
  if (words.length >= 2) return `${words[0][0]}${words[1][0]}`.toUpperCase();
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return '??';
}

function selectNode(node: ManagerNode) {
  if (selectedManagerId.value === node.id) {
    selectedManagerId.value = null;
  } else {
    selectedManagerId.value = node.id;
    selectedAllianceKey.value = null;
  }
}

function selectEdge(edge: GraphEdge) {
  if (selectedAllianceKey.value === edge.key) {
    selectedAllianceKey.value = null;
  } else {
    selectedAllianceKey.value = edge.key;
    selectedManagerId.value = null;
  }
}

function selectPartnerCard(partner: TopTradePartner) {
  const key = makeAllianceKey(partner.manager_a_id, partner.manager_b_id);
  if (selectedAllianceKey.value === key) {
    selectedAllianceKey.value = null;
  } else {
    selectedAllianceKey.value = key;
    selectedManagerId.value = null;
  }
}

function resetSelection() {
  selectedManagerId.value = null;
  selectedAllianceKey.value = null;
}

function isNodeHighlighted(nodeId: number): boolean {
  if (isPlaying.value && !isAllTimeView.value && activeNodeA.value && activeNodeB.value) {
    return activeNodeA.value.id === nodeId || activeNodeB.value.id === nodeId;
  }
  if (selectedManagerId.value != null) {
    if (selectedManagerId.value === nodeId) return true;
    const selectedNode = graphData.value.nodes.find((n) => n.id === selectedManagerId.value);
    return selectedNode ? selectedNode.partnerIds.has(nodeId) : false;
  }
  if (selectedAllianceKey.value != null) {
    const edge = graphData.value.edges.find((e) => e.key === selectedAllianceKey.value);
    return edge ? edge.source.id === nodeId || edge.target.id === nodeId : false;
  }
  return true;
}

function isEdgeHighlighted(edge: GraphEdge): boolean {
  if (isPlaying.value && !isAllTimeView.value && activeEdgeKey.value) {
    return activeEdgeKey.value === edge.key;
  }
  if (selectedAllianceKey.value != null) {
    return edge.key === selectedAllianceKey.value;
  }
  if (selectedManagerId.value != null) {
    return edge.source.id === selectedManagerId.value || edge.target.id === selectedManagerId.value;
  }
  return true;
}

function isPartnerSelected(partner: TopTradePartner): boolean {
  return selectedAllianceKey.value === makeAllianceKey(partner.manager_a_id, partner.manager_b_id);
}

const activeAlliancePartner = computed<TopTradePartner | null>(() => {
  if (!selectedAllianceKey.value) return null;
  const edge = graphData.value.edges.find((e) => e.key === selectedAllianceKey.value);
  return edge?.partner ?? null;
});

const activeManager = computed<ManagerNode | null>(() => {
  if (selectedManagerId.value == null) return null;
  return graphData.value.nodes.find((n) => n.id === selectedManagerId.value) ?? null;
});

const relevantTrades = computed<TradeDetail[]>(() => {
  if (selectedAllianceKey.value != null) {
    const parts = selectedAllianceKey.value.split('-').map(Number);
    if (parts.length === 2) {
      const [idA, idB] = parts;
      return props.trades.filter(
        (t) =>
          t.sides.some((s) => s.manager_id === idA) &&
          t.sides.some((s) => s.manager_id === idB)
      );
    }
  }

  if (selectedManagerId.value != null) {
    const id = selectedManagerId.value;
    return props.trades.filter((t) => t.sides.some((s) => s.manager_id === id));
  }

  return [];
});
</script>

<template>
  <div class="space-y-5">
    <!-- REPLAY THEATER CARD (when trades exist in this scope) -->
    <div
      v-if="playbackTrades.length > 0"
      class="rounded-2xl border border-slate-800/80 bg-slate-900/40 overflow-hidden relative"
    >
      <!-- Timeline progress bar -->
      <div v-if="!isAllTimeView" class="h-1 bg-slate-800/60 overflow-hidden">
        <div
          class="h-full bg-emerald-500 transition-all duration-75"
          :style="{ width: `${isPlaying ? tradeProgress : 0}%` }"
        />
      </div>

      <!-- Playback Controls Bar -->
      <div class="p-3.5 sm:p-4 space-y-3">
        <div class="flex items-center justify-between gap-2 flex-wrap">
          <!-- Stepper cluster -->
          <div class="flex items-center gap-1.5">
            <button
              type="button"
              class="h-9 px-3.5 rounded-lg text-xs font-bold transition-all shadow-sm cursor-pointer flex items-center gap-1.5"
              :class="
                isPlaying
                  ? 'bg-amber-500 text-slate-950 hover:bg-amber-400'
                  : 'bg-emerald-600 text-white hover:bg-emerald-500'
              "
              @click="togglePlay"
            >
              <Pause v-if="isPlaying" class="w-3.5 h-3.5 fill-current" />
              <Play v-else class="w-3.5 h-3.5 fill-current" />
              <span>{{ isPlaying ? 'Pause' : 'Play Flow' }}</span>
            </button>

            <button
              type="button"
              class="w-9 h-9 rounded-lg text-slate-400 hover:text-white bg-slate-900 hover:bg-slate-800 border border-slate-800 flex items-center justify-center transition-colors cursor-pointer"
              title="Previous trade"
              @click="prevTrade"
            >
              <ChevronLeft class="w-4 h-4" />
            </button>

            <button
              type="button"
              class="w-9 h-9 rounded-lg text-slate-400 hover:text-white bg-slate-900 hover:bg-slate-800 border border-slate-800 flex items-center justify-center transition-colors cursor-pointer"
              title="Next trade"
              @click="nextTrade"
            >
              <ChevronRight class="w-4 h-4" />
            </button>

            <button
              type="button"
              class="w-9 h-9 rounded-lg text-slate-400 hover:text-white bg-slate-900 hover:bg-slate-800 border border-slate-800 flex items-center justify-center transition-colors cursor-pointer"
              title="Reset to first"
              @click="resetPlayback"
            >
              <RotateCcw class="w-3.5 h-3.5" />
            </button>
          </div>

          <!-- Right side: Mobile View Mode & Speed -->
          <div class="flex items-center gap-2">
            <!-- Mobile View Toggle: Flow Card vs SVG Map -->
            <div class="flex md:hidden items-center rounded-lg bg-slate-900 border border-slate-800 p-0.5 text-xs font-semibold">
              <button
                type="button"
                class="px-2.5 py-1 rounded-md transition-all cursor-pointer"
                :class="mobileViewMode === 'duel' ? 'bg-slate-700 text-white' : 'text-slate-400'"
                @click="mobileViewMode = 'duel'"
              >
                Card Flow
              </button>
              <button
                type="button"
                class="px-2.5 py-1 rounded-md transition-all cursor-pointer"
                :class="mobileViewMode === 'graph' ? 'bg-slate-700 text-white' : 'text-slate-400'"
                @click="mobileViewMode = 'graph'"
              >
                Map
              </button>
            </div>

            <!-- Speed Toggle -->
            <div class="hidden sm:inline-flex items-center rounded-lg bg-slate-900 border border-slate-800 p-0.5 text-xs font-mono font-bold">
              <button
                type="button"
                class="px-2 py-1 rounded-md transition-all cursor-pointer"
                :class="playbackSpeed === 'slow' ? 'bg-slate-700 text-white' : 'text-slate-400 hover:text-slate-200'"
                @click="setSpeed('slow')"
              >
                Slow
              </button>
              <button
                type="button"
                class="px-2 py-1 rounded-md transition-all cursor-pointer"
                :class="playbackSpeed === 'normal' ? 'bg-slate-700 text-white' : 'text-slate-400 hover:text-slate-200'"
                @click="setSpeed('normal')"
              >
                Normal
              </button>
              <button
                type="button"
                class="px-2 py-1 rounded-md transition-all cursor-pointer"
                :class="playbackSpeed === 'fast' ? 'bg-slate-700 text-white' : 'text-slate-400 hover:text-slate-200'"
                @click="setSpeed('fast')"
              >
                Fast
              </button>
            </div>
          </div>
        </div>

        <!-- Trade jump picker (Clean native select overlay on mobile, zero overflow) -->
        <div class="flex items-center justify-between text-xs pt-1 border-t border-slate-800/80">
          <label class="relative flex items-center gap-1.5 font-mono text-slate-300 font-bold cursor-pointer">
            <span class="text-slate-500">Trade</span>
            <span class="text-emerald-400">{{ currentTradeIndex + 1 }}</span>
            <span class="text-slate-500">of {{ playbackTrades.length }}</span>
            <span v-if="activeTrade" class="text-slate-400 font-normal">
              ({{ activeTrade.week === 0 ? 'Preseason' : `Wk ${activeTrade.week}` }})
            </span>
            <ChevronDown class="w-3.5 h-3.5 text-slate-500" />
            <select
              aria-label="Jump to trade"
              class="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
              :value="currentTradeIndex"
              @change="goToTrade(Number(($event.target as HTMLSelectElement).value))"
            >
              <option
                v-for="(t, idx) in playbackTrades"
                :key="t.trade_id"
                :value="idx"
              >
                Trade #{{ idx + 1 }} ({{ t.week === 0 ? 'Preseason' : `Wk ${t.week}` }}) – {{ t.sides[0]?.team_name }} ⇄ {{ t.sides[1]?.team_name }}
              </option>
            </select>
          </label>

          <span v-if="activeTrade?.verdict_label" class="text-[11px] text-slate-400 truncate max-w-[200px]">
            {{ activeTrade.verdict_label }}
          </span>
        </div>
      </div>

      <!-- VIEW A: INTERACTIVE FLOW CARDS (Shown on mobile by default, or anytime duel is toggled) -->
      <div
        v-if="activeTrade && (mobileViewMode === 'duel' || !isAllTimeView)"
        class="p-3.5 sm:p-4 space-y-3 bg-slate-950/60 border-t border-slate-800/80"
        :class="mobileViewMode === 'duel' ? 'block' : 'block md:hidden'"
      >
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 items-stretch">
          <!-- Side A -->
          <div class="bg-slate-900/80 border border-slate-800 rounded-xl p-3 flex flex-col justify-between space-y-2">
            <div class="space-y-2">
              <div class="flex items-center gap-2.5">
                <TeamAvatar :src="activeSideA?.logo_url" :name="activeSideA?.team_name || activeSideA?.manager_name" size="sm" />
                <div class="min-w-0 flex-1">
                  <div class="text-xs font-bold text-slate-100 truncate">{{ activeSideA?.team_name }}</div>
                  <div class="text-[10px] text-slate-500 truncate">{{ activeSideA?.manager_name }}</div>
                </div>
              </div>

              <!-- Assets received -->
              <div class="space-y-1.5 pt-2 border-t border-slate-800/80">
                <div class="text-[10px] font-mono uppercase font-bold text-emerald-400">
                  Receives ({{ (activeSideA?.assets_received.length || 0) + (activeSideA?.faab_received ? 1 : 0) }})
                </div>
                <div
                  v-for="asset in activeSideA?.assets_received"
                  :key="asset.player_id"
                  class="flex items-center justify-between gap-1.5 text-xs text-slate-200"
                >
                  <span class="truncate">{{ getAssetDisplayName(asset) }}</span>
                  <span class="text-[10px] font-mono font-bold" :class="positionTextClass(asset.default_position)">
                    {{ asset.default_position }}
                  </span>
                </div>
                <div v-if="activeSideA?.faab_received" class="text-xs text-amber-300 font-mono">
                  +${{ activeSideA.faab_received }} FAAB
                </div>
              </div>
            </div>

            <div v-if="activeSideA && activeSideA.total_trade_score > 0" class="text-[11px] font-mono text-emerald-400 pt-1">
              +{{ activeSideA.total_trade_score.toFixed(1) }} value
            </div>
          </div>

          <!-- Side B -->
          <div class="bg-slate-900/80 border border-slate-800 rounded-xl p-3 flex flex-col justify-between space-y-2">
            <div class="space-y-2">
              <div class="flex items-center gap-2.5">
                <TeamAvatar :src="activeSideB?.logo_url" :name="activeSideB?.team_name || activeSideB?.manager_name" size="sm" />
                <div class="min-w-0 flex-1">
                  <div class="text-xs font-bold text-slate-100 truncate">{{ activeSideB?.team_name }}</div>
                  <div class="text-[10px] text-slate-500 truncate">{{ activeSideB?.manager_name }}</div>
                </div>
              </div>

              <!-- Assets received -->
              <div class="space-y-1.5 pt-2 border-t border-slate-800/80">
                <div class="text-[10px] font-mono uppercase font-bold text-slate-300">
                  Receives ({{ (activeSideB?.assets_received.length || 0) + (activeSideB?.faab_received ? 1 : 0) }})
                </div>
                <div
                  v-for="asset in activeSideB?.assets_received"
                  :key="asset.player_id"
                  class="flex items-center justify-between gap-1.5 text-xs text-slate-200"
                >
                  <span class="truncate">{{ getAssetDisplayName(asset) }}</span>
                  <span class="text-[10px] font-mono font-bold" :class="positionTextClass(asset.default_position)">
                    {{ asset.default_position }}
                  </span>
                </div>
                <div v-if="activeSideB?.faab_received" class="text-xs text-amber-300 font-mono">
                  +${{ activeSideB.faab_received }} FAAB
                </div>
              </div>
            </div>

            <div v-if="activeSideB && activeSideB.total_trade_score > 0" class="text-[11px] font-mono text-slate-300 pt-1">
              +{{ activeSideB.total_trade_score.toFixed(1) }} value
            </div>
          </div>
        </div>

        <!-- Breakdown prompt -->
        <button
          type="button"
          class="w-full h-9 rounded-xl bg-slate-900 hover:bg-slate-850 border border-slate-800 text-xs font-semibold text-slate-300 hover:text-white flex items-center justify-center gap-1.5 transition-colors cursor-pointer"
          @click="emit('select-trade', activeTrade)"
        >
          <span>View trade breakdown</span>
          <ExternalLink class="w-3.5 h-3.5 text-slate-500" />
        </button>
      </div>

      <!-- VIEW B: STADIUM SVG MAP (Shown on desktop, or when mobile toggles to Map) -->
      <div
        class="relative w-full overflow-hidden bg-slate-950 select-none max-h-[580px] border-t border-slate-800/80"
        :class="mobileViewMode === 'graph' ? 'block' : 'hidden md:block'"
        style="aspect-ratio: 960 / 580;"
      >
        <svg
          class="w-full h-full block relative z-0"
          :viewBox="`0 0 ${canvasWidth} ${canvasHeight}`"
          preserveAspectRatio="xMidYMid meet"
        >
          <defs>
            <filter id="neon-glow" x="-40%" y="-40%" width="180%" height="180%">
              <feGaussianBlur stdDeviation="5" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>

            <clipPath
              v-for="node in graphData.nodes"
              :id="'clip-avatar-' + node.id"
              :key="'clip-' + node.id"
            >
              <circle :cx="node.x" :cy="node.y" r="24" />
            </clipPath>
          </defs>

          <!-- Edges -->
          <g class="edges-group">
            <g
              v-for="edge in graphData.edges"
              :key="'edge-' + edge.key"
              class="cursor-pointer transition-all duration-300"
              :class="{
                'opacity-20': !isEdgeHighlighted(edge),
                'opacity-100': isEdgeHighlighted(edge),
              }"
              @click="selectEdge(edge)"
              @mouseenter="hoveredEdgeKey = edge.key"
              @mouseleave="hoveredEdgeKey = null"
            >
              <path
                :d="edge.pathD"
                fill="none"
                :stroke="
                  activeEdgeKey === edge.key
                    ? '#10b981'
                    : selectedAllianceKey === edge.key || hoveredEdgeKey === edge.key
                      ? '#6366f1'
                      : isAllTimeView && (!edge.source.isActive || !edge.target.isActive)
                        ? '#334155'
                        : '#4f46e5'
                "
                :stroke-width="edge.strokeWidth * (activeEdgeKey === edge.key ? 3.5 : 2.6)"
                stroke-linecap="round"
                :stroke-opacity="
                  activeEdgeKey === edge.key
                    ? 0.55
                    : selectedAllianceKey === edge.key
                      ? 0.45
                      : hoveredEdgeKey === edge.key
                        ? 0.35
                        : isAllTimeView && (!edge.source.isActive || !edge.target.isActive)
                          ? 0.04
                          : 0.12
                "
                :filter="isAllTimeView && (!edge.source.isActive || !edge.target.isActive) && selectedAllianceKey !== edge.key && hoveredEdgeKey !== edge.key ? undefined : 'url(#neon-glow)'"
              />

              <path
                :d="edge.pathD"
                fill="none"
                :stroke="
                  activeEdgeKey === edge.key
                    ? '#10b981'
                    : selectedAllianceKey === edge.key
                      ? '#34d399'
                      : hoveredEdgeKey === edge.key
                        ? '#818cf8'
                        : isAllTimeView && (!edge.source.isActive || !edge.target.isActive)
                          ? '#475569'
                          : '#6366f1'
                "
                :stroke-width="edge.strokeWidth"
                stroke-linecap="round"
                :stroke-opacity="
                  activeEdgeKey === edge.key
                    ? 0.95
                    : selectedAllianceKey === edge.key
                      ? 0.95
                      : hoveredEdgeKey === edge.key
                        ? 0.9
                        : isAllTimeView && (!edge.source.isActive || !edge.target.isActive)
                          ? 0.22
                          : Math.min(0.85, 0.45 + edge.tradeCount * 0.12)
                "
              />

              <path
                :d="edge.pathD"
                fill="none"
                stroke="transparent"
                stroke-width="26"
              />

              <g :transform="`translate(${edge.midX}, ${edge.midY})`">
                <circle
                  cx="0"
                  cy="0"
                  :r="activeEdgeKey === edge.key ? 13 : 10.5"
                  :fill="
                    activeEdgeKey === edge.key
                      ? '#064e3b'
                      : isAllTimeView && (!edge.source.isActive || !edge.target.isActive) && selectedAllianceKey !== edge.key && hoveredEdgeKey !== edge.key
                        ? '#080c14'
                        : '#090d16'
                  "
                  :stroke="
                    activeEdgeKey === edge.key
                      ? '#10b981'
                      : selectedAllianceKey === edge.key || hoveredEdgeKey === edge.key
                        ? '#818cf8'
                        : isAllTimeView && (!edge.source.isActive || !edge.target.isActive)
                          ? '#334155'
                          : '#475569'
                  "
                  :stroke-width="activeEdgeKey === edge.key || selectedAllianceKey === edge.key ? 2 : 1.5"
                />
                <text
                  x="0"
                  y="0"
                  text-anchor="middle"
                  dominant-baseline="central"
                  class="font-mono font-black select-none pointer-events-none"
                  :class="
                    activeEdgeKey === edge.key
                      ? 'text-xs fill-emerald-300'
                      : isAllTimeView && (!edge.source.isActive || !edge.target.isActive) && selectedAllianceKey !== edge.key && hoveredEdgeKey !== edge.key
                        ? 'text-[10px] fill-slate-500'
                        : 'text-[11px] fill-white'
                  "
                >
                  {{ edge.tradeCount }}
                </text>
              </g>
            </g>
          </g>

          <!-- Nodes -->
          <g class="nodes-group">
            <g
              v-for="node in graphData.nodes"
              :key="'node-' + node.id"
              class="cursor-pointer transition-all duration-300"
              :class="{
                'opacity-20': !isNodeHighlighted(node.id),
                'opacity-100': isNodeHighlighted(node.id) && (!isAllTimeView || node.isActive || selectedManagerId === node.id || hoveredNodeId === node.id),
                'opacity-35 hover:opacity-100': isAllTimeView && !node.isActive && isNodeHighlighted(node.id) && selectedManagerId !== node.id && hoveredNodeId !== node.id,
              }"
              @click="selectNode(node)"
              @mouseenter="hoveredNodeId = node.id"
              @mouseleave="hoveredNodeId = null"
            >
              <circle
                :cx="node.x"
                :cy="node.y"
                r="31"
                fill="none"
                :stroke="
                  activeNodeA?.id === node.id
                    ? '#10b981'
                    : activeNodeB?.id === node.id
                      ? '#818cf8'
                      : selectedManagerId === node.id || hoveredNodeId === node.id
                        ? '#38bdf8'
                        : isAllTimeView && !node.isActive
                          ? '#334155'
                          : '#4f46e5'
                "
                :stroke-width="isAllTimeView && !node.isActive && selectedManagerId !== node.id && hoveredNodeId !== node.id ? 1.5 : 3"
                :stroke-opacity="
                  activeNodeA?.id === node.id || activeNodeB?.id === node.id || selectedManagerId === node.id
                    ? 0.95
                    : hoveredNodeId === node.id
                      ? 0.8
                      : isAllTimeView && !node.isActive
                        ? 0.3
                        : 0.35
                "
                :filter="
                  activeNodeA?.id === node.id || activeNodeB?.id === node.id || selectedManagerId === node.id || hoveredNodeId === node.id
                    ? 'url(#neon-glow)'
                    : undefined
                "
              />

              <circle
                :cx="node.x"
                :cy="node.y"
                r="25"
                :fill="isAllTimeView && !node.isActive ? '#0b101b' : '#1e293b'"
                :stroke="isAllTimeView && !node.isActive ? '#1e293b' : '#0f172a'"
                stroke-width="2"
              />

              <image
                v-if="node.avatarUrl"
                :href="node.avatarUrl"
                :x="node.x - 25"
                :y="node.y - 25"
                width="50"
                height="50"
                preserveAspectRatio="xMidYMid slice"
                :clip-path="'url(#clip-avatar-' + node.id + ')'"
                :style="isAllTimeView && !node.isActive && selectedManagerId !== node.id && hoveredNodeId !== node.id ? 'filter: grayscale(85%) contrast(85%); opacity: 0.6;' : ''"
              />
              <text
                v-else
                :x="node.x"
                :y="node.y"
                text-anchor="middle"
                dominant-baseline="central"
                class="font-black text-xs font-mono select-none pointer-events-none"
                :class="isAllTimeView && !node.isActive ? 'fill-slate-500' : 'fill-slate-200'"
              >
                {{ getInitials(node.teamName || node.name) }}
              </text>

              <g :transform="`translate(${node.x + 15}, ${node.y - 18})`">
                <circle
                  cx="0"
                  cy="0"
                  r="10"
                  :fill="
                    activeNodeA?.id === node.id
                      ? '#059669'
                      : isAllTimeView && !node.isActive && selectedManagerId !== node.id
                        ? '#1e293b'
                        : '#4f46e5'
                  "
                  :stroke="isAllTimeView && !node.isActive && selectedManagerId !== node.id ? '#334155' : '#0f172a'"
                  stroke-width="1.5"
                />
                <text
                  x="0"
                  y="0"
                  text-anchor="middle"
                  dominant-baseline="central"
                  class="font-mono text-[9px] font-bold select-none pointer-events-none"
                  :class="isAllTimeView && !node.isActive && selectedManagerId !== node.id ? 'fill-slate-400' : 'fill-white'"
                >
                  {{ node.totalTrades }}
                </text>
              </g>

              <g :transform="`translate(${node.x}, ${node.y + 36})`">
                <rect
                  x="-70"
                  :y="isAllTimeView && !node.isActive ? -15 : -12"
                  width="140"
                  :height="isAllTimeView && !node.isActive ? 30 : 24"
                  rx="7"
                  :fill="isAllTimeView && !node.isActive ? '#060a12' : '#090d16'"
                  :stroke="
                    activeNodeA?.id === node.id
                      ? '#10b981'
                      : activeNodeB?.id === node.id
                        ? '#818cf8'
                        : selectedManagerId === node.id
                          ? '#38bdf8'
                          : isAllTimeView && !node.isActive
                            ? '#334155'
                            : '#475569'
                  "
                  :stroke-width="activeNodeA?.id === node.id || selectedManagerId === node.id ? 2 : 1.5"
                  :stroke-opacity="isAllTimeView && !node.isActive && selectedManagerId !== node.id ? 0.45 : 0.8"
                />
                <text
                  x="0"
                  :y="isAllTimeView && !node.isActive ? -4 : 0"
                  text-anchor="middle"
                  dominant-baseline="central"
                  class="font-sans text-[11px] font-bold tracking-tight select-none pointer-events-none"
                  :class="isAllTimeView && !node.isActive ? 'fill-slate-400 font-medium' : 'fill-slate-100'"
                >
                  {{ (node.teamName || node.name).length > 17 ? (node.teamName || node.name).slice(0, 15) + '…' : (node.teamName || node.name) }}
                </text>
                <text
                  v-if="isAllTimeView && !node.isActive"
                  x="0"
                  y="7"
                  text-anchor="middle"
                  dominant-baseline="central"
                  class="font-mono text-[7.5px] uppercase font-bold tracking-widest fill-slate-500 select-none pointer-events-none"
                >
                  Inactive
                </text>
              </g>
            </g>
          </g>
        </svg>

        <!-- Floating Player Tokens (Animated Replay) -->
        <div
          v-if="!isAllTimeView"
          class="absolute inset-0 pointer-events-none overflow-hidden z-20"
        >
          <div
            v-for="item in activeFlowItems"
            :key="`${animKey}-${item.id}`"
            class="player-flow-token absolute transform -translate-x-1/2 -translate-y-1/2 flex items-center gap-2 px-2.5 py-1 rounded-full shadow-2xl backdrop-blur-md border transition-all"
            :class="
              item.direction === 'B_TO_A'
                ? 'bg-slate-950/95 border-emerald-500/80 shadow-emerald-950/80'
                : 'bg-slate-950/95 border-indigo-500/80 shadow-indigo-950/80'
            "
            :style="item.style"
          >
            <div
              class="w-7 h-7 rounded-full overflow-hidden shrink-0 flex items-center justify-center border"
              :class="item.direction === 'B_TO_A' ? 'border-emerald-500/50 bg-emerald-950/60' : 'border-indigo-500/50 bg-indigo-950/60'"
            >
              <img
                v-if="item.headshotUrl && !failedHeadshots[item.id]"
                :src="item.headshotUrl"
                :alt="item.name"
                class="w-full h-full object-cover"
                @error="handleHeadshotError(item.id)"
              />
              <span
                v-else
                class="text-[9px] font-black font-mono"
                :class="item.direction === 'B_TO_A' ? 'text-emerald-300' : 'text-indigo-300'"
              >
                {{ item.isFaab ? '$' : item.position.slice(0, 3) }}
              </span>
            </div>

            <div class="flex items-center gap-1.5 min-w-0 pr-1">
              <span class="text-xs font-bold text-slate-100 whitespace-nowrap">{{ item.name }}</span>
              <span class="text-[9px] font-mono font-bold uppercase" :class="positionTextClass(item.position)">
                {{ item.position }}
              </span>
            </div>

            <div class="text-[10px] font-mono font-black shrink-0 px-1.5 py-0.5 rounded-full bg-slate-800 text-slate-200">
              <span v-if="item.score > 0">+{{ item.score.toFixed(1) }}</span>
              <ArrowRight v-else class="w-3 h-3 text-slate-400" />
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- EMPTY STATE -->
    <div
      v-else-if="partners.length === 0 && trades.length === 0"
      class="rounded-2xl border border-slate-800/80 py-12 px-6 text-center space-y-2"
    >
      <div class="w-10 h-10 rounded-xl bg-slate-900 border border-slate-800 flex items-center justify-center mx-auto text-slate-500">
        <Info class="w-5 h-5" />
      </div>
      <h4 class="text-sm font-semibold text-slate-200">No trades to visualize</h4>
      <p class="text-xs text-slate-500 max-w-sm mx-auto">
        No completed trades in {{ seasonLabel.toLowerCase() }}.
      </p>
    </div>

    <!-- FILTERED LEDGER (when a corridor/node is tapped) -->
    <div
      v-if="selectedManagerId != null || selectedAllianceKey != null"
      class="rounded-2xl border border-slate-800/80 bg-slate-900/40 p-4 space-y-3"
    >
      <div class="flex items-center justify-between gap-2 border-b border-slate-800/80 pb-2.5">
        <div>
          <h3 class="text-xs font-bold uppercase tracking-wider text-slate-200 flex items-center gap-2">
            <ArrowLeftRight class="w-3.5 h-3.5 text-emerald-400" />
            <span v-if="activeAlliancePartner">
              {{ activeAlliancePartner.manager_a_name }} ⇄ {{ activeAlliancePartner.manager_b_name }}
            </span>
            <span v-else-if="activeManager">
              {{ activeManager.teamName || activeManager.name }}
            </span>
          </h3>
          <p class="text-[11px] text-slate-500 mt-0.5">
            {{ relevantTrades.length }} {{ relevantTrades.length === 1 ? 'trade' : 'trades' }}
          </p>
        </div>

        <button
          type="button"
          class="text-xs font-semibold text-slate-400 hover:text-white flex items-center gap-1 cursor-pointer"
          @click="resetSelection"
        >
          <RotateCcw class="w-3 h-3" />
          <span>Clear filter</span>
        </button>
      </div>

      <div v-if="relevantTrades.length > 0" class="space-y-3">
        <TradeAutopsyCard
          v-for="trade in relevantTrades"
          :key="trade.trade_id"
          :trade="trade"
          @select="emit('select-trade', trade)"
        />
      </div>
      <p v-else class="text-xs text-slate-500 italic py-2 text-center">
        No trade records match this corridor filter.
      </p>
    </div>

    <!-- ALLIANCES GRID -->
    <section class="space-y-3">
      <div class="flex items-baseline justify-between px-0.5">
        <h3 class="text-[11px] font-bold uppercase tracking-wider text-slate-400">
          Frequent Trade Partners ({{ partners.length }})
        </h3>
        <span class="text-[11px] text-slate-500">Tap to isolate corridor</span>
      </div>

      <div v-if="partners.length > 0" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        <TradePartnerAllianceCard
          v-for="(partner, idx) in partners"
          :key="`${partner.manager_a_id}-${partner.manager_b_id}`"
          :partner="partner"
          :rank="idx + 1"
          :selected="isPartnerSelected(partner)"
          :is-inactive-a="isAllTimeView && !isManagerActive(partner.manager_a_id)"
          :is-inactive-b="isAllTimeView && !isManagerActive(partner.manager_b_id)"
          @select="selectPartnerCard"
        />
      </div>
      <p v-else class="text-xs text-slate-500 italic py-4 text-center">
        No partner alliances recorded yet.
      </p>
    </section>
  </div>
</template>

<style scoped>
@keyframes flowBetweenNodes {
  0% {
    left: var(--startX);
    top: var(--startY);
    opacity: 0;
    transform: translate(-50%, -50%) scale(0.35);
  }
  12% {
    opacity: 1;
    transform: translate(-50%, -50%) scale(1);
  }
  50% {
    left: var(--midX);
    top: var(--midY);
    opacity: 1;
    transform: translate(-50%, -50%) scale(1.06);
  }
  85% {
    left: var(--endX);
    top: var(--endY);
    opacity: 1;
    transform: translate(-50%, -50%) scale(1);
  }
  95% {
    opacity: 0.85;
    transform: translate(-50%, -50%) scale(0.85);
  }
  100% {
    left: var(--endX);
    top: var(--endY);
    opacity: 0;
    transform: translate(-50%, -50%) scale(0.35);
  }
}

.player-flow-token {
  animation: flowBetweenNodes var(--duration) cubic-bezier(0.22, 1, 0.36, 1) 1 forwards;
  animation-delay: var(--delay);
}
</style>
