<script setup>
defineProps({
	title: { type: String, required: true },
	subtitle: { type: String, default: "" },
	breadcrumbs: { type: Array, default: () => [] },
})
</script>

<template>
	<div class="cp-page-header">
		<nav v-if="breadcrumbs.length" class="cp-breadcrumbs">
			<template v-for="(crumb, index) in breadcrumbs" :key="index">
				<RouterLink v-if="crumb.to" :to="crumb.to">{{ crumb.label }}</RouterLink>
				<span v-else>{{ crumb.label }}</span>
				<i v-if="index < breadcrumbs.length - 1">›</i>
			</template>
		</nav>
		<div class="cp-page-title">
			<div>
				<h1>{{ title }}</h1>
				<p v-if="subtitle">{{ subtitle }}</p>
			</div>
			<div class="cp-actions"><slot name="actions" /></div>
		</div>
	</div>
</template>
