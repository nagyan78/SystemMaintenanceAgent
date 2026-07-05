<script setup lang="ts">
import { computed, onMounted } from "vue";
import { useRoute } from "vue-router";
import {
  BrainCircuit,
  FileUp,
  GitBranch,
  Home,
  Layers3,
  ListChecks,
  Network,
  Settings,
  ShieldCheck
} from "@lucide/vue";
import AppLogo from "../components/AppLogo.vue";
import { refreshFiles, workspace } from "../stores/workspace";

const route = useRoute();

const navItems = [
  { to: "/overview", label: "首页概览", icon: Home },
  { to: "/upload", label: "文件上传", icon: FileUp },
  { to: "/tree", label: "体系概览", icon: Layers3 },
  { to: "/diagnosis/structure", label: "结构诊断", icon: Network },
  { to: "/diagnosis/content", label: "内容诊断", icon: ListChecks },
  { to: "/suggestions", label: "智能建议", icon: BrainCircuit },
  { to: "/quality", label: "质量评价", icon: ShieldCheck },
  { to: "/versions", label: "版本管理", icon: GitBranch },
  { to: "/settings", label: "系统设置", icon: Settings }
];

const pageTitle = computed(() => String(route.meta.title ?? "工作台"));

onMounted(async () => {
  try {
    await refreshFiles();
  } catch {
    // The active page shows API failures where it can act on them.
  }
});
</script>

<template>
  <div class="workspace-shell">
    <aside class="sidebar">
      <RouterLink class="brand-block brand-block--link" to="/overview" aria-label="返回首页概览">
        <AppLogo />
        <div>
          <h1>标准产品体系维护智能体平台</h1>
          <p>本地 Web + 本地智能体网关 + 本地数据库</p>
        </div>
      </RouterLink>

      <nav class="side-nav" aria-label="主导航">
        <RouterLink
          v-for="item in navItems"
          :key="item.to"
          class="side-nav__item"
          active-class="side-nav__item--active"
          :to="item.to"
        >
          <component :is="item.icon" :size="20" :stroke-width="1.9" />
          <span>{{ item.label }}</span>
        </RouterLink>
      </nav>
    </aside>

    <main class="main-stage">
      <header class="topbar">
        <div class="topbar__title">
          <AppLogo />
          <div>
            <h2>{{ pageTitle }}</h2>
            <p>标准产品体系维护智能体平台</p>
          </div>
        </div>
        <div class="topbar__badges">
          <span class="topbar__badge"><span class="status-dot"></span>{{ workspace.loadingFiles ? "连接中" : "本地运行" }}</span>
        </div>
      </header>

      <RouterView />
    </main>
  </div>
</template>
