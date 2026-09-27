<script setup>
import { computed, onMounted, ref } from "vue"
import { call } from "@/api"
import { docStatusLabel, formatCurrency, formatDate } from "@/utils"
import StatusPill from "@/components/StatusPill.vue"

// Desk's "Connections" tab: linked doctypes grouped as ERPNext's dashboard config groups them.
const props = defineProps({ doctype: { type: String, required: true }, docname: { type: String, required: true } })
const groups = ref([])
const loading = ref(true)
const collapsed = ref({})

const APP_PATHS = { "Purchase Order": "/purchase-orders", "Purchase Receipt": "/receipts", "Purchase Invoice": "/invoices", "Stock Entry": "/transfers" }
const total = computed(() => groups.value.reduce((sum, group) => sum + group.items.reduce((count, item) => count + item.count, 0), 0))

function deskUrl(doctype, name) {
	return `/app/${doctype.toLowerCase().replace(/ /g, "-")}/${encodeURIComponent(name)}`
}

function status(doc) {
	return "docstatus" in doc ? docStatusLabel(doc) : doc.status || ""
}

function toggle(doctype) {
	collapsed.value = { ...collapsed.value, [doctype]: !collapsed.value[doctype] }
}

async function load() {
	loading.value = true
	try {
		groups.value = await call("get_document_connections", { doctype: props.doctype, name: props.docname })
		// long lists start folded so the panel stays scannable
		const folded = {}
		for (const group of groups.value) for (const item of group.items) folded[item.doctype] = item.count > 5
		collapsed.value = folded
	} catch {
		groups.value = []
	} finally {
		loading.value = false
	}
}

defineExpose({ load })
onMounted(load)
</script>

<template>
	<section class="cp-card">
		<header class="cp-card-head"><h3>Connections</h3><span class="cp-muted">{{ loading ? "Loading…" : total ? `${total} linked` : "" }}</span></header>
		<p v-if="!loading && !groups.length" class="cp-empty-row">No linked documents yet.</p>
		<div v-else class="cp-connections">
			<div v-for="group in groups" :key="group.label" class="cp-connection-group">
				<h4>{{ group.label }}</h4>
				<div v-for="item in group.items" :key="item.doctype" class="cp-connection">
					<button type="button" class="cp-connection-head" :aria-expanded="!collapsed[item.doctype]" @click="toggle(item.doctype)">
						<svg viewBox="0 0 24 24" :class="{ open: !collapsed[item.doctype] }"><path d="m9 6 6 6-6 6" /></svg>
						<span>{{ item.doctype }}</span>
						<em>{{ item.count }}</em>
					</button>
					<ul v-if="!collapsed[item.doctype]">
						<li v-for="doc in item.documents" :key="doc.name">
							<div>
								<RouterLink v-if="APP_PATHS[item.doctype]" :to="`${APP_PATHS[item.doctype]}/${doc.name}`" class="cp-link">{{ doc.name }}</RouterLink>
								<a v-else :href="deskUrl(item.doctype, doc.name)" target="_blank" class="cp-link">{{ doc.name }} ↗</a>
								<small>{{ [doc.title && !String(doc.title).includes("{") ? doc.title : "", formatDate(doc.date)].filter(Boolean).join(" · ") }}</small>
							</div>
							<StatusPill v-if="status(doc)" :status="status(doc)" />
							<span class="cp-connection-amount">{{ doc.amount != null ? formatCurrency(doc.amount) : "" }}</span>
						</li>
					</ul>
				</div>
			</div>
		</div>
	</section>
</template>
