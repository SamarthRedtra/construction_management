<script setup>
import { toasts } from "@/toast"
</script>

<template>
	<div class="cp-toasts" aria-live="polite">
		<div v-for="item in toasts" :key="item.id" class="cp-toast" :class="item.tone">{{ item.message }}</div>
	</div>
</template>
