import { createRouter, createWebHistory } from 'vue-router'
import type { RouteLocationNormalizedLoaded } from 'vue-router'
import UploadView from '../views/UploadView.vue'
import WorkflowView from '../views/WorkflowView.vue'
import ReviewView from '../views/ReviewView.vue'
import VersionsView from '../views/VersionsView.vue'
import ReportView from '../views/ReportView.vue'
import OverviewView from '../views/OverviewView.vue'
import TreeView from '../views/TreeView.vue'
import DiagnosisView from '../views/DiagnosisView.vue'
import EvaluationView from '../views/EvaluationView.vue'
import TriageView from '../views/TriageView.vue'

const routes = [
  { path: '/', redirect: '/upload' },
  { path: '/upload', component: UploadView },
  { path: '/workflow/:taskId', component: WorkflowView, props: true },
  { path: '/review/:reviewBatchId', component: ReviewView, props: (route: RouteLocationNormalizedLoaded) => ({ reviewBatchId: route.params.reviewBatchId, taskId: route.query.task_id ?? '' }) },
  { path: '/versions', component: VersionsView },
  { path: '/report/:versionId', component: ReportView, props: true },
  { path: '/overview/:versionId', component: OverviewView, props: true },
  { path: '/tree/:versionId', component: TreeView, props: true },
  { path: '/diagnosis/:versionId', component: DiagnosisView, props: true },
  { path: '/evaluation', component: EvaluationView },
  { path: '/triage', component: TriageView },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior() {
    return { top: 0 }
  },
})

export default router
