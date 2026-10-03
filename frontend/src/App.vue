<script setup>
import { onMounted, ref } from "vue"
import { useRouter } from "vue-router"
import { call } from "@/api"
import { session } from "@/utils"
import AppShell from "@/components/AppShell.vue"
import Toasts from "@/components/Toasts.vue"

const loading = ref(true)
const error = ref("")
const router = useRouter()

onMounted(async () => {
	try {
		session.context = await call("get_workspace_context")
		if (!session.context.can_purchase && !session.context.can_transfer && router.currentRoute.value.path === "/dashboard") {
			router.replace(session.context.can_approve_lpo ? "/lpo-approvals" : "/catalog")
		}
	} catch (requestError) {
		error.value = requestError.message || "Unable to load Controlled Procurement."
	} finally {
		loading.value = false
	}
})
</script>

<template>
	<div v-if="loading" class="cp-boot">Loading Controlled Procurement…</div>
	<div v-else-if="error" class="cp-boot cp-boot-error">
		<strong>Controlled Procurement is unavailable</strong>
		<p>{{ error }}</p>
		<a href="/desk">Back to Desk</a>
	</div>
	<AppShell v-else>
		<RouterView :key="`${$route.fullPath}:${session.version}`" />
	</AppShell>
	<Toasts />
</template>
