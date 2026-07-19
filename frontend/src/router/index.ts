import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import UploadView from '../views/UploadView.vue'
import WorkflowView from '../views/WorkflowView.vue'
import VersionsView from '../views/VersionsView.vue'
import ReportView from '../views/ReportView.vue'
import OverviewView from '../views/OverviewView.vue'
import TreeView from '../views/TreeView.vue'
import DiagnosisView from '../views/DiagnosisView.vue'

const routes: RouteRecordRaw[] = [
  { path: '/', redirect: '/upload' },
  { path: '/upload', component: UploadView },
  { path: '/workflow/:taskId', component: WorkflowView, props: true },
  { path: '/workflows', redirect: '/upload' },
  { path: '/reviews', redirect: '/versions' },
  { path: '/review/:reviewBatchId', redirect: '/versions' },
  { path: '/versions', component: VersionsView },
  { path: '/report', component: ReportView },
  { path: '/report/:versionId', component: ReportView },
  { path: '/overview/:versionId', component: OverviewView, props: true },
  { path: '/tree/:versionId', component: TreeView, props: true },
  { path: '/diagnosis', component: DiagnosisView },
  { path: '/diagnosis/:versionId', component: DiagnosisView, props: true },
  { path: '/evaluation/:versionId?', redirect: route => route.params.versionId ? `/report/${route.params.versionId}` : (route.query.version_id ? `/report/${route.query.version_id}` : '/versions') },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior() {
    return { top: 0 }
  },
})

export default router
