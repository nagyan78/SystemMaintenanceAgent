import { createRouter, createWebHistory } from "vue-router";
import WorkbenchLayout from "../views/WorkbenchLayout.vue";
import UploadView from "../views/UploadView.vue";
import OverviewView from "../views/OverviewView.vue";
import PlaceholderView from "../views/PlaceholderView.vue";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", redirect: "/upload" },
    {
      path: "/",
      component: WorkbenchLayout,
      children: [
        { path: "/upload", component: UploadView, meta: { title: "文件上传" } },
        { path: "/overview", component: OverviewView, meta: { title: "首页概览" } },
        {
          path: "/tree",
          component: PlaceholderView,
          props: { eyebrow: "体系概览", title: "产品体系树", status: "等待分类树接口" }
        },
        {
          path: "/diagnosis/structure",
          component: PlaceholderView,
          props: { eyebrow: "结构诊断", title: "结构问题", status: "等待诊断接口" }
        },
        {
          path: "/diagnosis/content",
          component: PlaceholderView,
          props: { eyebrow: "内容诊断", title: "内容问题", status: "等待诊断接口" }
        },
        {
          path: "/suggestions",
          component: PlaceholderView,
          props: { eyebrow: "智能建议", title: "调整建议", status: "等待建议接口" }
        },
        {
          path: "/quality",
          component: PlaceholderView,
          props: { eyebrow: "质量评价", title: "体系质量分", status: "等待评价接口" }
        },
        {
          path: "/versions",
          component: PlaceholderView,
          props: { eyebrow: "版本管理", title: "版本记录", status: "等待版本接口" }
        },
        {
          path: "/settings",
          component: PlaceholderView,
          props: { eyebrow: "系统设置", title: "系统设置", status: "暂无可配置项" }
        }
      ]
    }
  ]
});

export default router;
