import { createRouter, createWebHistory } from 'vue-router';
import type { RouteRecordRaw } from 'vue-router';

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'standings',
    component: () => import('@/views/StandingsView.vue'),
    meta: { title: 'Standings' },
  },
  {
    path: '/earnings',
    name: 'earnings',
    component: () => import('@/views/EarningsView.vue'),
    meta: { title: 'Earnings' },
  },
  {
    path: '/head-to-head',
    name: 'head-to-head',
    component: () => import('@/views/HeadToHeadView.vue'),
    meta: { title: 'Head-to-Head' },
  },
  {
    path: '/trades',
    name: 'trades',
    component: () => import('@/views/TradesView.vue'),
    meta: { title: 'Trades' },
  },
  {
    path: '/waivers',
    name: 'waivers',
    component: () => import('@/views/WaiversView.vue'),
    meta: { title: 'Waivers' },
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/',
  },
];

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
  scrollBehavior(_to, _from, savedPosition) {
    if (savedPosition) {
      return savedPosition;
    }
    return { top: 0 };
  },
});

export default router;
