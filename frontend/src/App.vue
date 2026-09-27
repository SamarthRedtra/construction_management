<script setup>
import { onMounted, ref } from "vue"
import { call } from "@/api"
import { session } from "@/utils"
import AppShell from "@/components/AppShell.vue"
import Toasts from "@/components/Toasts.vue"

const loading = ref(true)
const error = ref("")

onMounted(async () => {
	try {
		session.context = await call("get_workspace_context")
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
