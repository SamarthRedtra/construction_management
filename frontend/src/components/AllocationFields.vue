<script setup>
import { companyFilters } from "@/utils"
import { onMounted, ref, watch } from "vue"
import { call } from "@/api"
import LinkSelect from "@/components/LinkSelect.vue"

const props = defineProps({ modelValue: { type: Object, required: true } })
const emit = defineEmits(["update:modelValue"])
const bills = ref([])
const items = ref([])

function update(field, value) {
	emit("update:modelValue", { ...props.modelValue, [field]: value })
}

async function loadOptions() {
	if (!props.modelValue.project) {
		bills.value = []
		items.value = []
		return
	}
	const result = await call("get_boq_options", { project: props.modelValue.project, bill_no: props.modelValue.bill_no || "" })
	bills.value = result.bills
	items.value = result.items
}

watch(() => props.modelValue.project, async (project, previous) => {
	if (project !== previous) emit("update:modelValue", { project, bill_no: "", boq_item: "" })
	await loadOptions()
})
watch(() => props.modelValue.bill_no, async () => {
	await loadOptions()
	if (props.modelValue.boq_item && !items.value.some((item) => item.name === props.modelValue.boq_item)) update("boq_item", "")
})
onMounted(loadOptions)
</script>

<template>
	<div class="cp-grid-3">
		<LinkSelect :model-value="modelValue.project" doctype="Project" label="Project" :required="true" @update:model-value="update('project', $event)" :filters="companyFilters()" />
		<label class="cp-field">
			<span>Bill No<i>*</i></span>
			<select class="cp-input" :value="modelValue.bill_no" :disabled="!modelValue.project" required @change="update('bill_no', $event.target.value)">
				<option value="">{{ modelValue.project ? "Select Bill No" : "Select a project first" }}</option>
				<option v-for="bill in bills" :key="bill.name" :value="bill.name">{{ bill.bill_no || bill.name }}</option>
			</select>
		</label>
		<label class="cp-field">
			<span>BOQ Item<i>*</i></span>
			<select class="cp-input" :value="modelValue.boq_item" :disabled="!modelValue.bill_no" required @change="update('boq_item', $event.target.value)">
				<option value="">{{ modelValue.bill_no ? "Select BOQ Item" : "Select a bill first" }}</option>
				<option v-for="item in items" :key="item.name" :value="item.name">{{ item.description || item.name }}</option>
			</select>
		</label>
	</div>
</template>
