<script setup>
import { computed } from "vue"

const props = defineProps({ status: { type: String, default: "" } })

const tone = computed(() => {
	const value = (props.status || "").toLowerCase()
	if (["draft"].includes(value)) return "neutral"
	if (value === "open po") return "info"
	if (["cancelled", "closed", "overdue"].includes(value)) return "danger"
	if (["completed", "delivered", "received", "paid"].includes(value) || value.startsWith("to bill")) return "success"
	if (value.startsWith("to receive") || ["partly received", "on hold", "unpaid", "partly paid"].includes(value)) return "warning"
	return "info"
})
</script>

<template>
	<span class="cp-pill" :class="tone">{{ status || "—" }}</span>
</template>
