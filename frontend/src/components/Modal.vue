<script setup>
import { onBeforeUnmount, onMounted } from "vue"

defineProps({
	title: { type: String, required: true },
	// md 520px · lg 720px · xl 1040px; `wide` is the older name for lg
	size: { type: String, default: "md" },
	wide: { type: Boolean, default: false },
})
const emit = defineEmits(["close"])

function onKey(event) {
	if (event.key === "Escape") emit("close")
}
onMounted(() => document.addEventListener("keydown", onKey))
onBeforeUnmount(() => document.removeEventListener("keydown", onKey))
</script>

<template>
	<Teleport to="body">
		<div class="cp-modal-backdrop" @mousedown.self="emit('close')">
			<section class="cp-modal" :class="`size-${wide ? 'lg' : size}`" role="dialog" :aria-label="title">
				<header>
					<h2>{{ title }}</h2>
					<button class="cp-close" aria-label="Close" @click="emit('close')">×</button>
				</header>
				<div class="cp-modal-body"><slot /></div>
				<footer v-if="$slots.footer"><slot name="footer" /></footer>
			</section>
		</div>
	</Teleport>
</template>
