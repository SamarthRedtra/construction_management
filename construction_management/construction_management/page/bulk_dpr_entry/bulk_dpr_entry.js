frappe.pages['bulk-dpr-entry'].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Bulk DPR Entry',
		single_column: true
	});

	// Load Vue 3
	frappe.require('/assets/frappe/node_modules/vue/dist/vue.global.js').then(() => {
		new BulkDPREntry(wrapper, page);
	});
}

class BulkDPREntry {
	constructor(wrapper, page) {
		this.wrapper = $(wrapper);
		this.page = page;
		this.project = frappe.utils.get_query_params().project;

		// Handle route options if passed
		if (frappe.route_options && frappe.route_options.project) {
			this.project = frappe.route_options.project;
		}

		this.setup_app();
	}

	setup_app() {
		const me = this;

		// Ensure mount point exists
		this.wrapper.html(`
			<div class="bulk-dpr-entry-wrapper">
				<div id="bulk-dpr-app"></div>
			</div>
		`);

		// Ensure Vue is available
		if (typeof Vue === 'undefined' && window.Vue) {
			// It is on window, so acceptable
		} else if (typeof Vue === 'undefined') {
			console.error("Vue is not loaded.");
			frappe.msgprint("Error: Vue library not loaded.");
			return;
		}

		const { createApp, ref, computed, onMounted, onUnmounted, watch } = window.Vue;

		const App = {
			setup() {
				const project = ref(me.project);
				const date = ref(frappe.datetime.get_today());
				const loading = ref(false);
				const rows = ref([]);
				const masterData = ref({
					boq_items: [],
					sites: [],
					employees: [],
					materials: [],
					overhead_accounts: []
				});

				const boqItemsMap = computed(() => {
					const map = {};
					masterData.value.boq_items.forEach(item => {
						map[item.name] = item;
					});
					return map;
				});

				const allSelected = computed({
					get: () => rows.value.length > 0 && rows.value.every(r => r.selected),
					set: (val) => rows.value.forEach(r => r.selected = val)
				});

				const hasSelection = computed(() => rows.value.some(r => r.selected));

				// Calculate real-time balance
				const getAvailableBalance = (boqItemName) => {
					if (!boqItemName || !boqItemsMap.value[boqItemName]) return 0;

					const item = boqItemsMap.value[boqItemName];
					const originalBalance = item.balance || 0; // Assuming API returns 'balance' which is (Total - Billed) or similar qty

					// Subtract quantities used in CURRENT rows
					const usedInRows = rows.value.reduce((acc, row) => {
						if (row.boq_item === boqItemName && row.area_covered) {
							return acc + parseFloat(row.area_covered);
						}
						return acc;
					}, 0);

					return originalBalance - usedInRows;
				};

				const computedMaterialOptions = computed(() => {
					// Create a map of usage counts
					const usageMap = {};
					rows.value.forEach(row => {
						if (Array.isArray(row.materials)) {
							row.materials.forEach(mat => {
								let itemCode, usedQty;
								if (typeof mat === 'object' && mat !== null) {
									itemCode = mat.name || mat.item_code; // using name/item_code as valueField
									usedQty = parseFloat(mat.qty) || 0;
								} else {
									itemCode = mat;
									usedQty = 1;
								}

								if (itemCode) {
									usageMap[itemCode] = (usageMap[itemCode] || 0) + usedQty;
								}
							});
						}
					});

					// Return materials with adjusted balance
					return masterData.value.materials.map(mat => {
						const usedQty = usageMap[mat.name] || 0;
						// Ensure we have a numeric balance to start with
						const originalBalance = parseFloat(mat.balance) || 0;
						return {
							...mat,
							balance: Math.max(0, originalBalance - usedQty) // Prevent negative for display? Or show negative? User said "deduct".
						};
					});
				});

				const fetchData = async () => {
					if (!project.value) return;
					loading.value = true;

					try {
						const r = await frappe.call({
							method: 'construction_management.construction_management.page.bulk_dpr_entry.bulk_dpr_entry.get_initial_data',
							args: { project: project.value, date: date.value }
						});
						if (r.message) {
							masterData.value = r.message;
							// Initialize rows with existing DPRs if any, or empty row
							if (r.message.existing_dprs && r.message.existing_dprs.length) {
								rows.value = r.message.existing_dprs.map(dpr => ({
									...dpr,
									selected: false,
									// ensure multiselects are arrays
									employees: dpr.employees || [],
									materials: dpr.materials || [],
									overheads: dpr.overheads || [],
									remarks: dpr.comment || ''
								}));
							} else {
								rows.value = [];
								addRow();
							}
						}
					} catch (e) {
						console.error(e);
						frappe.msgprint(__('Error fetching data'));
					} finally {
						loading.value = false;
					}
				};

				const addRow = () => {
					rows.value.push({
						selected: false,
						boq_item: '',
						site: '',
						area_covered: 0,
						employees: [],
						materials: [],
						overheads: [],
						remarks: ''
					});
				};

				const removeRow = (index) => {
					rows.value.splice(index, 1);
				};

				const save = async (submit = false) => {
					loading.value = true;

					// If submit is true, we only process SELECTED rows, unless none selected then all?
					// "submit where i can select the row" implies explicit selection.
					// Let's say: Save = All rows. Submit = Selected rows (if any) or Confirm All?
					// Strategy: 
					// Save: Saves ALL rows.
					// Submit: Submits SELECTED rows. If none selected, warn user / submit nothing? Or ask to submit all?
					// Let's implement: Submit requires selection.

					let rowsToProcess = rows.value;
					if (submit) {
						const selected = rows.value.filter(r => r.selected);
						if (selected.length === 0) {
							frappe.msgprint("Please select rows to submit.");
							loading.value = false;
							return;
						}
						rowsToProcess = selected;
					}

					try {
						await frappe.call({
							method: 'construction_management.construction_management.page.bulk_dpr_entry.bulk_dpr_entry.save_bulk_dpr',
							args: {
								project: project.value,
								date: date.value,
								rows: rowsToProcess,
								submit: submit
							}
						});
						frappe.show_alert({ message: submit ? 'Submitted successfully' : 'Saved successfully', indicator: 'green' });
						fetchData(); // Refresh to get updated statuses
					} catch (e) {
						frappe.msgprint(__('Error processing DPRs'));
						console.error(e);
					} finally {
						loading.value = false;
					}
				};

				const submitSelected = () => {
					frappe.confirm('Are you sure you want to Submit selected DPRs?', () => {
						save(true);
					});
				};

				watch(project, () => {
					fetchData();
					me.page.set_title_sub(project.value);
				});

				onMounted(() => {
					// Initialize Project Link Field
					const $wrapper = me.wrapper.find('#project-field-wrapper');
					if ($wrapper.length) {
						me.projectField = frappe.ui.form.make_control({
							parent: $wrapper,
							df: {
								label: 'Project',
								fieldname: 'project',
								fieldtype: 'Link',
								options: 'Project',
								placeholder: 'Select Project',
								get_query: function () {
									return {
										filters: {
											enable_progressive_boq: 1
										}
									};
								},
								change: () => {
									project.value = me.projectField.get_value();
								}
							},
							render_input: true
						});

						if (project.value) {
							me.projectField.set_value(project.value);
						}
					}

					if (project.value) fetchData();

					// Setup Page Actions
					me.page.set_primary_action('Save', () => save(false));
					me.page.add_inner_button('Submit Selected', submitSelected);
				});

				return {
					project,
					date,
					loading,
					rows,
					masterData,
					boqItemsMap,
					computedMaterialOptions,
					getAvailableBalance,
					allSelected,
					hasSelection,
					addRow,
					removeRow,
					save,
					submitSelected
				};
			},
			template: `
				<div class="bulk-dpr-app">
					<div class="filters mb-3">
							<div class="row">
							<div class="col-md-4">
								<div id="project-field-wrapper" style="height: 38px;"></div>
							</div>
							<div class="col-md-3">
								<label>Date</label>
								<input type="date" class="form-control" v-model="date" @change="fetchData">
							</div>
                            <div class="col-md-5 text-right pt-4">
                                <!-- Actions moved to page menu, but can keep some here if needed -->
                            </div>
							</div>
					</div>

                    <div v-if="loading" class="text-center p-4">Loading...</div>
					<div v-else class="dpr-table-container">
						<table class="table table-bordered table-striped">
							<thead>
								<tr>
                                    <th style="width: 3%" class="text-center">
                                        <input type="checkbox" v-model="allSelected">
                                    </th>
									<th style="width: 20%">BOQ Item / Balance</th>
									<th style="width: 12%">Site</th>
									<th style="width: 8%">Area</th>
									<th style="width: 18%">Employees</th>
									<th style="width: 18%">Materials</th>
									<th style="width: 12%">Overheads</th>
                                    <th style="width: 12%">Remarks</th>
									<th style="width: 3%"></th>
								</tr>
							</thead>
							<tbody>
								<tr v-for="(row, idx) in rows" :key="idx">
                                    <td class="text-center align-middle">
                                        <input type="checkbox" v-model="row.selected">
                                    </td>
									<td>
                                        <select class="form-control input-sm mb-1" v-model="row.boq_item">
                                            <option value="">Select Item</option>
                                            <option v-for="item in masterData.boq_items" :value="item.name">
                                                {{ item.item_code }} - {{ item.description }}
                                            </option>
                                        </select>
                                        <div class="text-muted small" v-if="row.boq_item">
                                            Balance: {{ getAvailableBalance(row.boq_item).toFixed(2) }} {{ boqItemsMap[row.boq_item]?.unit }}
                                        </div>
                                    </td>
									<td>
                                         <select class="form-control input-sm" v-model="row.site">
                                            <option value="">Select Site</option>
                                            <option v-for="site in masterData.sites" :value="site.name">
                                                {{ site.site_name }}
                                            </option>
                                        </select>
                                    </td>
									<td>
                                        <input type="number" class="form-control input-sm" v-model.number="row.area_covered" step="0.01">
                                    </td>
									<td>
                                        <!-- Multiselect Employees -->
                                        <SimpleMultiselect 
                                            :options="masterData.employees" 
                                            v-model="row.employees"
                                            label-field="employee_name"
                                            value-field="name"
                                            placeholder="Add Employees"
                                        />
                                    </td>
									<td>
                                         <!-- Multiselect Materials -->
                                        <SimpleMultiselect 
                                            :options="computedMaterialOptions" 
                                            v-model="row.materials"
                                            label-field="item_name"
                                            value-field="name"
                                            :with-quantity="true"
                                             placeholder="Add Materials"
                                        />
                                    </td>
									<td>
                                        <!-- Multiselect Overheads -->
                                        <SimpleMultiselect 
                                            :options="masterData.overhead_accounts" 
                                            v-model="row.overheads"
                                            label-field="account_name"
                                            value-field="name"
                                            :with-quantity="true"
                                            prompt-label="Amount"
                                             placeholder="Add Overheads"
                                        />
                                    </td>
                                    <td>
                                        <textarea class="form-control input-sm" v-model="row.remarks" rows="2" placeholder="Remarks"></textarea>
                                    </td>
									<td class="text-center align-middle">
                                        <button class="btn btn-danger btn-xs" @click="removeRow(idx)">
                                            X
                                        </button>
                                    </td>
								</tr>
							</tbody>
						</table>
			<button class="btn btn-secondary btn-sm" @click="addRow">Add Row</button>
					</div>
				</div>
			`
		};

		// Simple Multiselect Component
		const SimpleMultiselect = {
			props: ['options', 'modelValue', 'labelField', 'valueField', 'placeholder', 'withQuantity', 'promptLabel'],
			emits: ['update:modelValue'],
			setup(props, { emit }) {
				const isOpen = ref(false);
				const searchQuery = ref('');
				const searchInput = ref(null);
				const rootEl = ref(null);

				const filteredOptions = computed(() => {
					if (!searchQuery.value) return props.options;
					const q = searchQuery.value.toLowerCase();
					return props.options.filter(opt => {
						const label = (opt[props.labelField] || '').toLowerCase();
						const val = (opt[props.valueField] || '').toLowerCase();
						return label.includes(q) || val.includes(q);
					});
				});

				const selectedItems = computed(() => {
					if (props.withQuantity) {
						// Model value is array of objects
						return (props.modelValue || []).map(item => {
							// Find updated info from options if needed, but item has qty
							const opt = props.options.find(o => o[props.valueField] === item[props.valueField]);
							return {
								...item,
								[props.labelField]: opt ? opt[props.labelField] : (item[props.labelField] || item[props.valueField])
							};
						});
					}
					return (props.modelValue || []).map(val => {
						return props.options.find(opt => opt[props.valueField] === val) || { [props.labelField]: val };
					});
				});

				const toggle = () => {
					isOpen.value = !isOpen.value;
					if (isOpen.value) {
						searchQuery.value = '';
						setTimeout(() => {
							if (searchInput.value) searchInput.value.focus();
						}, 100);
					}
				};

				const closeIfClickedOutside = (event) => {
					if (!isOpen.value) return;
					if (rootEl.value && !rootEl.value.contains(event.target)) {
						isOpen.value = false;
					}
				};

				onMounted(() => {
					document.addEventListener('click', closeIfClickedOutside);
				});

				onUnmounted(() => {
					document.removeEventListener('click', closeIfClickedOutside);
				});

				const select = (opt) => {
					const current = [...(props.modelValue || [])];

					if (props.withQuantity) {
						// Check if already selected?
						if (current.some(i => i[props.valueField] === opt[props.valueField])) {
							frappe.msgprint("Item already added. Please remove to edit.");
							return;
						}

						// Close dropdown immediately
						isOpen.value = false;

						const label = props.promptLabel || 'Quantity';

						frappe.prompt({
							label: label,
							fieldname: 'qty',
							fieldtype: 'Float',
							reqd: 1,
							default: 1
						}, (values) => {
							const parsedQty = parseFloat(values.qty);
							if (isNaN(parsedQty) || parsedQty <= 0) {
								frappe.msgprint("Invalid value");
								return;
							}

							current.push({
								[props.valueField]: opt[props.valueField],
								[props.labelField]: opt[props.labelField],
								qty: parsedQty, // We keep 'qty' as internal key for simplicity, or we could make it dynamic but mapping is easier
								amount: parsedQty // Duplicate to amount if it's overhead
							});
							emit('update:modelValue', current);
						}, `Enter ${label} for ${opt[props.labelField]}`, 'Add');

						return;
					}

					const val = opt[props.valueField];
					if (!current.includes(val)) {
						current.push(val);
					}
					emit('update:modelValue', current);
					isOpen.value = false;
				};

				const remove = (val) => {
					if (props.withQuantity) {
						const current = (props.modelValue || []).filter(v => v[props.valueField] !== val);
						emit('update:modelValue', current);
					} else {
						const current = (props.modelValue || []).filter(v => v !== val);
						emit('update:modelValue', current);
					}
				};

				return { isOpen, selectedItems, toggle, select, remove, searchQuery, filteredOptions, searchInput, rootEl };
			},
			template: `
				<div class="simple-multiselect position-relative" ref="rootEl">
					<div class="multiselect-input form-control input-sm" @click="toggle" style="height: auto; min-height: 30px; cursor: pointer;">
                        <span v-if="!selectedItems.length" class="text-muted">{{ placeholder }}</span>
                        <div v-else class="selected-tags d-flex flex-wrap gap-1">
                            <span v-for="item in selectedItems" :key="item[valueField]" class="badge badge-primary" style="white-space: normal; text-align: left;">
                                {{ item[labelField] }}
                                <span v-if="item.qty" class="ml-1 font-weight-bold">({{ item.qty }})</span>
                                <span class="ml-1 cursor-pointer" @click.stop="remove(item[valueField] || item)">&times;</span>
                            </span>
                        </div>
                    </div>
			<div v-if="isOpen" class="multiselect-dropdown position-absolute bg-white border shadow-sm" style="z-index: 1000; width: 100%; max-height: 300px; overflow-y: auto;">
                <div class="p-2 border-bottom sticky-top bg-white">
                    <input type="text" class="form-control input-sm" v-model="searchQuery" placeholder="Search..." ref="searchInput" @click.stop>
                </div>
				<div v-for="opt in filteredOptions" :key="opt[valueField]"
				class="dropdown-item p-2 cursor-pointer hover-bg-light border-bottom" style="white-space: normal; word-break: break-word;"
                            @click="select(opt)">
				{{ opt[labelField] }}
                <span v-if="opt.balance !== undefined" class="text-muted small ml-1">
                    (Avail: {{ opt.balance }} {{ opt.stock_uom }})
                </span>
			</div>
                <div v-if="filteredOptions.length === 0" class="p-2 text-muted text-center small">No matches found</div>
                    </div>
                </div>
			`
		};

		const app = createApp(App);
		app.component('SimpleMultiselect', SimpleMultiselect);
		app.mount(this.wrapper.find('#bulk-dpr-app')[0]);
	}
}
