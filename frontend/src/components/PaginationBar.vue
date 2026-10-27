<script setup>
import { computed } from "vue"

const props = defineProps({
	page: { type: Number, required: true },
	pageSize: { type: Number, required: true },
	total: { type: Number, required: true },
	loading: { type: Boolean, default: false },
})

const emit = defineEmits(["update:page"])

const totalPages = computed(() => Math.max(1, Math.ceil(props.total / props.pageSize) || 1))
const from = computed(() => (props.total === 0 ? 0 : (props.page - 1) * props.pageSize + 1))
const to = computed(() => Math.min(props.page * props.pageSize, props.total))

const pageNumbers = computed(() => {
	const current = props.page
	const last = totalPages.value
	const windowSize = 5
	let start = Math.max(1, current - Math.floor(windowSize / 2))
	let end = Math.min(last, start + windowSize - 1)
	start = Math.max(1, end - windowSize + 1)
	const pages = []
	for (let n = start; n <= end; n += 1) pages.push(n)
	return pages
})

function go(next) {
	const page = Math.min(Math.max(1, next), totalPages.value)
	if (page === props.page || props.loading) return
	emit("update:page", page)
}
</script>

<template>
	<footer v-if="total > 0" class="cp-card-foot cp-pagination">
		<span class="cp-pagination-meta">Showing {{ from }}–{{ to }} of {{ total }}</span>
		<nav v-if="total > pageSize" class="cp-pagination-nav" aria-label="Pagination">
			<button type="button" class="cp-btn sm" :disabled="loading || page <= 1" @click="go(page - 1)">Prev</button>
			<button
				v-for="n in pageNumbers"
				:key="n"
				type="button"
				class="cp-btn sm cp-page-btn"
				:class="{ primary: n === page }"
				:disabled="loading"
				:aria-current="n === page ? 'page' : undefined"
				@click="go(n)"
			>{{ n }}</button>
			<button type="button" class="cp-btn sm" :disabled="loading || page >= totalPages" @click="go(page + 1)">Next</button>
		</nav>
	</footer>
</template>
