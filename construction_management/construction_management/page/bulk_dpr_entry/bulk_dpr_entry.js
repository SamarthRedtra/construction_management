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
				const defaultCompany = frappe.defaults.get_user_default('Company') || frappe.defaults.get_user_default('company');
				const company = ref(defaultCompany || '');
				const project = ref(me.project);
				const date = ref(frappe.datetime.get_today());
				const loading = ref(false);
				const rows = ref([]);
				const currentPage = ref(1);
				const pageSize = ref(20);
				const pageSizeOptions = ref([20, 50, 100]);
				const totalRows = ref(0);
				const masterData = ref({
					boq_items: [],
					sites: [],
					employees: [],
					materials: [],
					assets: [],
					overhead_accounts: []
				});

				// paginatedRows is now the same as rows since rows only holds current page
				const paginatedRows = computed(() => rows.value);

				const totalPages = computed(() => Math.ceil(totalRows.value / pageSize.value) || 1);

				const summaryTotals = computed(() => {
					let labour = 0, material = 0, asset = 0, overhead = 0, total = 0;
					rows.value.forEach(row => {
						labour += parseFloat(row.labour_cost || 0);
						material += parseFloat(row.material_cost || 0);
						asset += parseFloat(row.asset_cost || 0);
						overhead += parseFloat(row.overhead_cost || 0);
						total += parseFloat(row.total_cost || 0);
					});
					return { labour, material, asset, overhead, total };
				});

				const boqItemsMap = computed(() => {
					const map = {};
					masterData.value.boq_items.forEach(item => {
						map[item.name] = item;
					});
					return map;
				});

				const employeeRatesMap = computed(() => {
					const map = {};
					masterData.value.employees.forEach(emp => {
						map[emp.name] = emp.rate_per_day || 0;
					});
					return map;
				});

				// Options for absent employees (reference only, no hours/cost) - strip rate to skip prompt
				const absentEmployeeOptions = computed(() => (masterData.value.employees || []).map(e => ({ name: e.name, employee_name: e.employee_name })));

				const assetRatesMap = computed(() => {
					const map = {};
					masterData.value.assets.forEach(asset => {
						map[asset.name] = {
							hour: asset.rate_per_hour || 0,
							day: asset.rate_per_day || 0
						};
					});
					return map;
				});

				const allSelected = computed({
					get: () => rows.value.length > 0 && paginatedRows.value.every(r => r.selected),
					set: (val) => paginatedRows.value.forEach(r => r.selected = val)
				});

				const hasSelection = computed(() => rows.value.some(r => r.selected));
				const hasDraftSelection = computed(() => rows.value.some(r => r.selected && r.docstatus === 0));
				const hasSubmittedSelection = computed(() => rows.value.some(r => r.selected && r.docstatus === 1));

				// Role-based cost visibility: only Purchase Manager, Accounts Manager, Accounts User see costs
				const showCosts = ref((frappe.user_roles || []).some(r => ['Purchase Manager', 'Accounts Manager', 'Accounts User'].includes(r)));

				// Calculate costs for a row
				const calculateRowCosts = (row) => {
					// Labour Cost
					let labour = 0;
					(row.employees || []).forEach(emp => {
						const rate = employeeRatesMap.value[typeof emp === 'object' ? emp.employee : emp] || 0;
						const hours = parseFloat(emp.hours || 8);
						labour += rate * (hours / 8);
					});
					row.labour_cost = labour;

					// Material Cost
					let material = 0;
					(row.materials || []).forEach(mat => {
						const rate = parseFloat(mat.rate || 0);
						const qty = parseFloat(mat.qty || 0);
						material += rate * qty;
					});
					row.material_cost = material;

					// Asset Cost (Simplified for bulk, assuming 8 hours default if not specified)
					let asset = 0;
					(row.assets || []).forEach(a => {
						const rate = assetRatesMap.value[a.asset]?.hour || 0;
						const hours = parseFloat(a.hours || 8);
						asset += rate * hours;
					});
					row.asset_cost = asset;

					// Overhead Cost
					let overhead = 0;
					(row.overheads || []).forEach(ovh => {
						overhead += parseFloat(ovh.amount || ovh.qty || 0);
					});
					row.overhead_cost = overhead;

					row.total_cost = labour + material + asset + overhead;
				};

				// Watch for changes in child arrays to recalculate
				watch(() => rows.value, (newRows) => {
					newRows.forEach(row => calculateRowCosts(row));
				}, { deep: true });

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
					return (masterData.value.materials || []).map(mat => {
						const usedQty = usageMap[mat.name] || 0;
						// Ensure we have a numeric balance to start with
						const originalBalance = parseFloat(mat.balance) || 0;
						const valuationRate = parseFloat(mat.valuation_rate) || 0;
						const displayLabel = showCosts.value
							? `${mat.item_name || mat.name} | Stock: ${originalBalance.toFixed(2)} | Rate: ${valuationRate.toFixed(2)}`
							: `${mat.item_name || mat.name} | Stock: ${originalBalance.toFixed(2)}`;
						return {
							...mat,
							display_label: displayLabel,
							valuation_rate: valuationRate,
							balance: Math.max(0, originalBalance - usedQty) // Prevent negative for display? Or show negative? User said "deduct".
						};
					});
				});

				const mastersLoadedFor = ref('');
				const PAGE_METHOD = 'construction_management.construction_management.page.bulk_dpr_entry.bulk_dpr_entry';

				const applyDayRows = (message) => {
					totalRows.value = message.total_dprs || 0;
					if (message.existing_dprs && message.existing_dprs.length) {
						rows.value = message.existing_dprs.map(dpr => ({
							...dpr,
							selected: false,
							site: dpr.site || '',
							area_covered: dpr.area_covered || 0,
							remarks: dpr.remarks || '',
							employees: dpr.employees || [],
							absent_employees: dpr.absent_employees || [],
							materials: (dpr.materials || []).map(m => ({
								...m,
								name: m.item_code,
								item_code: m.item_code
							})),
							overheads: (dpr.overheads || []).map(o => ({
								...o,
								name: o.account,
								account: o.account
							}))
						}));
					} else {
						rows.value = [];
						if (currentPage.value === 1) addRow();
					}
					rows.value.forEach(row => calculateRowCosts(row));
				};

				const fetchMasters = async () => {
					const r = await frappe.call({
						method: `${PAGE_METHOD}.get_master_data`,
						args: {
							project: project.value,
							company: company.value,
							date: date.value
						}
					});
					if (r.message) {
						masterData.value = r.message;
						mastersLoadedFor.value = project.value;
					}
				};

				const fetchDayRows = async (page = 1) => {
					const r = await frappe.call({
						method: `${PAGE_METHOD}.get_day_rows`,
						args: {
							project: project.value,
							company: company.value,
							date: date.value,
							start: (page - 1) * pageSize.value,
							page_length: pageSize.value
						}
					});
					if (r.message) {
						applyDayRows(r.message);
					}
				};

				const refreshAssetsForDate = async () => {
					const r = await frappe.call({
						method: `${PAGE_METHOD}.get_project_assets_with_rates`,
						args: { project: project.value, date: date.value }
					});
					if (r.message) {
						masterData.value = { ...masterData.value, assets: r.message };
					}
				};

				const fetchData = async (page = 1, reloadMasters = false) => {
					if (!project.value) return;
					loading.value = true;
					currentPage.value = page;
					try {
						if (reloadMasters || mastersLoadedFor.value !== project.value) {
							await fetchMasters();
						}
						await fetchDayRows(page);
					} catch (e) {
						console.error(e);
						frappe.msgprint(__('Error fetching data'));
					} finally {
						loading.value = false;
					}
				};

				const addRow = () => {
					rows.value.unshift({
						selected: false,
						docstatus: 0,
						boq_item: '',
						site: '',
						area_covered: 0,
						employees: [],
						absent_employees: [],
						materials: [],
						overheads: [],
						labour_cost: 0,
						material_cost: 0,
						asset_cost: 0,
						overhead_cost: 0,
						total_cost: 0,
						remarks: ''
					});
					// Note: totalRows.value++ if we want pagination to reflect added rows? 
					// Usually, added rows are just temporary.
				};

				const removeRow = async (idx) => {
					const row = rows.value[idx];
					if (row.name) {
						if (row.docstatus > 0) {
							frappe.msgprint(__('Cannot delete a submitted or cancelled DPR. Please cancel it first.'));
							return;
						}

						frappe.confirm(__('Are you sure you want to delete this DPR record ({0})?', [row.name]), async () => {
							loading.value = true;
							try {
								await frappe.db.delete("Daily Progress Record", row.name);
								rows.value.splice(idx, 1);
								totalRows.value--;
								frappe.show_alert({ message: __('DPR deleted'), indicator: 'green' });
							} catch (e) {
								console.error(e);
							} finally {
								loading.value = false;
							}
						});
					} else {
						rows.value.splice(idx, 1);
					}
				};

				const changePage = (newPage) => {
					if (newPage < 1 || newPage > totalPages.value) return;
					// Check for unsaved changes (simple check: any row without a name or any selected row?)
					const hasUnsaved = rows.value.some(r => !r.name || r.selected);
					if (hasUnsaved) {
						frappe.confirm('You have unsaved changes or selected rows. Changing the page will reload data. Continue?', () => {
							fetchData(newPage);
						});
					} else {
						fetchData(newPage);
					}
				};

				const changePageSize = () => {
					currentPage.value = 1;
					fetchData(1);
				};

				const save = async (submit = false) => {
					if (!project.value) {
						frappe.msgprint(__('Please select a project first'));
						return;
					}

					let rowsToProcess = [];
					if (submit) {
						const selected = rows.value.filter(r => r.selected && r.docstatus === 0);
						if (selected.length === 0) {
							frappe.msgprint(__('Please select Draft rows to submit.'));
							return;
						}
						rowsToProcess = selected;
					} else {
						// Save all modified or new rows that are not submitted
						rowsToProcess = rows.value.filter(r => r.docstatus === 0 && (r.name || r.boq_item));
						if (rowsToProcess.length === 0) {
							frappe.msgprint(__('No new or modified rows to save.'));
							return;
						}
					}

					// Mandatory: BOQ Item and Site must be filled for each row
					const invalidRows = rowsToProcess.filter(r => !r.boq_item || !r.site);
					if (invalidRows.length > 0) {
						frappe.msgprint(__('BOQ Item and Site are mandatory. Please fill both for all rows before saving.'));
						return;
					}

					loading.value = true;
					try {
						const res = await frappe.call({
							method: 'construction_management.construction_management.page.bulk_dpr_entry.bulk_dpr_entry.save_bulk_dpr',
							args: {
								project: project.value,
								date: date.value,
								rows: rowsToProcess,
								submit: submit
							}
						});

						if (res.message) {
							const result = res.message;
							const saved = Array.isArray(result) ? result : (result.saved_names || []);
							const errors = Array.isArray(result) ? [] : (result.errors || []);

							if (saved.length) {
								frappe.show_alert({
									message: __('{0} DPRs {1} successfully', [saved.length, submit ? 'submitted' : 'saved']),
									indicator: 'green'
								});
							}

							if (errors.length) {
								frappe.msgprint({
									title: __('Some DPRs failed'),
									message: errors.join('<br>'),
									indicator: 'orange'
								});
							}

							fetchData(currentPage.value, true);
						}
					} catch (e) {
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

				const fetchFromRoster = async (idx) => {
					if (!project.value || !date.value) {
						frappe.msgprint(__('Please select project and date first.'));
						return;
					}
					const row = rows.value[idx];
					if (row.docstatus > 0) {
						frappe.msgprint(__('Cannot modify submitted or cancelled DPR.'));
						return;
					}
					loading.value = true;
					try {
						const r = await frappe.call({
							method: 'construction_management.construction_management.page.bulk_dpr_entry.bulk_dpr_entry.get_workers_from_daily_roster',
							args: { project: project.value, date: date.value }
						});
						const workers = r.message || [];
						if (workers.length === 0) {
							frappe.msgprint(__('No workers found in Daily Roster for this project and date.'));
							return;
						}
						const existingIds = new Set((row.employees || []).map(e => (typeof e === 'object' ? e.employee : e) || e));
						const toAdd = workers.filter(w => !existingIds.has(w.employee));
						toAdd.forEach(w => {
							row.employees = row.employees || [];
							row.employees.push({
								employee: w.employee,
								name: w.employee,
								employee_name: w.employee_name,
								hours: 8,
								rate_per_day: w.rate_per_day || 0,
								amount: (w.rate_per_day || 0) * 1
							});
						});
						calculateRowCosts(row);
						frappe.show_alert({ message: __('{0} employees fetched from roster', [toAdd.length]), indicator: 'green' });
					} catch (e) {
						console.error(e);
						frappe.msgprint(__('Error fetching workers from roster'));
					} finally {
						loading.value = false;
					}
				};

				const cancelSelected = async () => {
					const selected = rows.value.filter(r => r.selected && r.docstatus === 1);
					if (selected.length === 0) {
						frappe.msgprint(__('Please select submitted rows to cancel.'));
						return;
					}

					frappe.confirm(__('Are you sure you want to Cancel {0} selected DPRs?', [selected.length]), async () => {
						loading.value = true;
						try {
							await frappe.call({
								method: 'construction_management.construction_management.page.bulk_dpr_entry.bulk_dpr_entry.cancel_bulk_dpr',
								args: { names: selected.map(r => r.name) }
							});
							frappe.show_alert({ message: __('DPRs cancelled successfully'), indicator: 'green' });
							fetchData(currentPage.value, true);
						} catch (e) {
							console.error(e);
						} finally {
							loading.value = false;
						}
					});
				};

				const deleteSelected = async () => {
					const selected = rows.value.filter(r => r.selected && (r.docstatus === 0 || !r.name));
					if (selected.length === 0) {
						frappe.msgprint(__('Please select draft rows to delete.'));
						return;
					}

					const named = selected.filter(r => r.name).map(r => r.name);
					const unnamed = selected.filter(r => !r.name);

					frappe.confirm(__('Delete {0} selected row(s)?', [selected.length]), async () => {
						if (named.length) {
							loading.value = true;
							try {
								const res = await frappe.call({
									method: 'construction_management.construction_management.page.bulk_dpr_entry.bulk_dpr_entry.delete_bulk_dpr',
									args: { names: named }
								});
								const deleted = res.message?.deleted || [];
								const errors = res.message?.errors || [];
								if (deleted.length) {
									frappe.show_alert({ message: __('{0} DPR(s) deleted', [deleted.length]), indicator: 'green' });
								}
								if (errors.length) {
									frappe.msgprint({ title: __('Delete errors'), message: errors.join('<br>'), indicator: 'orange' });
								}
							} catch (e) {
								console.error(e);
							} finally {
								loading.value = false;
							}
						}

						if (unnamed.length) {
							rows.value = rows.value.filter(r => !(r.selected && !r.name));
						}
						fetchData(currentPage.value, true);
					});
				};

				const toEmbedVideoUrl = (url) => {
					if (!url) return '';
					if (url.includes('youtube.com/watch')) {
						const id = new URL(url, window.location.origin).searchParams.get('v');
						return id ? `https://www.youtube.com/embed/${id}` : url;
					}
					if (url.includes('youtu.be/')) {
						const id = url.split('youtu.be/')[1]?.split(/[?&]/)[0];
						return id ? `https://www.youtube.com/embed/${id}` : url;
					}
					return url;
				};

				const showHelpVideo = () => {
					const videoUrl = toEmbedVideoUrl(masterData.value.help_video_url || '');
					const steps = `
						<ol style="margin: 0; padding-left: 18px; line-height: 1.6;">
							<li>${__('Select Company and Project, then choose the DPR date.')}</li>
							<li>${__('Click Add Row and pick a BOQ Item.')}</li>
							<li>${__('Select or add a Site, enter Area covered.')}</li>
							<li>${__('Add Employees, Materials, and Overheads as needed.')}</li>
							<li>${__('Save drafts, then Submit Selected when ready.')}</li>
						</ol>
					`;
					const videoHtml = videoUrl
						? `<div style="position:relative;padding-bottom:56.25%;height:0;overflow:hidden;border-radius:8px;margin-top:12px;">
							<iframe src="${videoUrl}" style="position:absolute;top:0;left:0;width:100%;height:100%;border:0;" allowfullscreen></iframe>
						</div>`
						: `<p class="text-muted" style="margin-top:12px;">${__('No help video configured. Set Bulk DPR Help Video URL in BOQ Settings for your company.')}</p>`;

					const dlg = new frappe.ui.Dialog({
						title: __('How to Create Bulk DPR'),
						size: 'large',
						fields: [{ fieldtype: 'HTML', fieldname: 'help_html' }]
					});
					dlg.fields_dict.help_html.$wrapper.html(`<div>${steps}${videoHtml}</div>`);
					dlg.show();
				};

				const showAddSiteDialog = (rowIdx = null) => {
					if (!project.value) {
						frappe.msgprint(__('Please select a project first.'));
						return;
					}
					const dlg = new frappe.ui.Dialog({
						title: __('Add Project Site'),
						fields: [
							{
								fieldname: 'site_name',
								label: __('Site Name'),
								fieldtype: 'Data',
								reqd: 1,
								description: __('Creates a new site under the selected project')
							}
						],
						primary_action_label: __('Create Site'),
						primary_action: async (values) => {
							loading.value = true;
							try {
								const res = await frappe.call({
									method: 'construction_management.construction_management.page.bulk_dpr_entry.bulk_dpr_entry.create_quick_project_site',
									args: { project: project.value, site_name: values.site_name }
								});
								const site = res.message || {};
								if (site.name) {
									const exists = (masterData.value.sites || []).some(s => s.name === site.name);
									if (!exists) {
										masterData.value.sites = [
											{ name: site.name, site_name: site.site_name || values.site_name },
											...(masterData.value.sites || [])
										];
									}
									if (rowIdx !== null && rows.value[rowIdx]) {
										rows.value[rowIdx].site = site.name;
									}
									frappe.show_alert({
										message: site.created ? __('Site created') : __('Site already exists'),
										indicator: 'green'
									});
									dlg.hide();
								}
							} catch (e) {
								console.error(e);
							} finally {
								loading.value = false;
							}
						}
					});
					dlg.show();
				};

				watch(project, () => {
					if (!project.value) {
						rows.value = [];
						totalRows.value = 0;
						mastersLoadedFor.value = '';
						masterData.value = {
							boq_items: [],
							sites: [],
							employees: [],
							materials: [],
							assets: [],
							overhead_accounts: []
						};
						return;
					}
					fetchData(1, true);
				});

				watch(date, async () => {
					if (!project.value) return;
					loading.value = true;
					currentPage.value = 1;
					try {
						await refreshAssetsForDate();
						await fetchDayRows(1);
					} catch (e) {
						console.error(e);
						frappe.msgprint(__('Error fetching data'));
					} finally {
						loading.value = false;
					}
				});

				onMounted(() => {
					// Initialize Company Link Field
					const $companyWrapper = me.wrapper.find('#company-field-wrapper');
					if ($companyWrapper.length) {
						me.companyField = frappe.ui.form.make_control({
							parent: $companyWrapper,
							df: {
								label: 'Company',
								fieldname: 'company',
								fieldtype: 'Link',
								options: 'Company',
								placeholder: 'Select Company',
								change: async () => {
									company.value = me.companyField.get_value();
									project.value = '';
									if (me.projectField) {
										me.projectField.set_value('');
									}
								}
							},
							render_input: true
						});

						if (company.value) {
							me.companyField.set_value(company.value);
						}
					}

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
											enable_progressive_boq: 1,
											...(company.value ? { company: company.value } : {})
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

					if (project.value && !company.value) {
						frappe.db.get_value('Project', project.value, 'company').then(r => {
							const projectCompany = r.message?.company;
							if (projectCompany) {
								company.value = projectCompany;
								if (me.companyField) {
									me.companyField.set_value(projectCompany);
								}
							}
							fetchData();
						});
					} else if (project.value) {
						fetchData();
					}

					// Setup Page Actions
					me.page.set_primary_action('Save', () => save(false));
					me.page.add_inner_button(__('How to Create DPR'), showHelpVideo);
					me.page.add_inner_button(__('Add Site'), () => showAddSiteDialog());
					me.page.add_inner_button('Submit Selected', submitSelected);
					me.page.add_inner_button('Delete Selected', deleteSelected);
					me.page.add_inner_button('Cancel Selected', cancelSelected);
				});

				return {
					company,
					project,
					date,
					loading,
					rows,
					paginatedRows,
					currentPage,
					totalPages,
					totalRows,
					pageSize,
					pageSizeOptions,
					summaryTotals,
					masterData,
					boqItemsMap,
					absentEmployeeOptions,
					computedMaterialOptions,
					getAvailableBalance,
					allSelected,
					hasSelection,
					hasDraftSelection,
					hasSubmittedSelection,
					showCosts,
					addRow,
					removeRow,
					save,
					fetchData,
					fetchFromRoster,
					submitSelected,
					cancelSelected,
					deleteSelected,
					showHelpVideo,
					showAddSiteDialog,
					changePageSize
				};
			},
			template: `
				<div class="bulk-dpr-app">
					<style>
						.bulk-dpr-app { background: #f8fafc; padding: 20px; border-radius: 12px; }
						.filters-card { background: white; padding: 20px; border-radius: 12px; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1); margin-bottom: 24px; }
						.dpr-table-container { background: white; border-radius: 12px; box-shadow: 0 10px 15px -3px rgb(0 0 0 / 0.1); overflow: hidden; }
						.table th { background: #f1f5f9; color: #475569; font-weight: 600; text-transform: uppercase; font-size: 11px; letter-spacing: 0.05em; padding: 12px 16px; border: none; }
						.table td { padding: 16px; vertical-align: top; border-color: #f1f5f9; }
						.form-control { border-radius: 6px; border: 1px solid #e2e8f0; transition: all 0.2s; }
						.compact-link .control-label { display: none !important; }
						.compact-link .control-input input { height: 32px; padding: 4px 8px; }
						.compact-link .control-input { min-height: 32px; }
						.compact-date { height: 32px; padding: 4px 8px; }
						.form-control:focus { border-color: #6366f1; box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1); }
						.btn-primary-modern { background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%); color: white; border: none; box-shadow: 0 4px 6px -1px rgba(79, 70, 229, 0.4); }
						.btn-secondary-modern { background: white; color: #475569; border: 1px solid #e2e8f0; }
						.badge-primary { background: #e0e7ff; color: #4338ca; border-radius: 4px; padding: 4px 8px; font-weight: 500; }
						.cost-card { background: #f8fafc; border-radius: 8px; padding: 10px; font-size: 12px; line-height: 1.6; }
						.cost-label { color: #64748b; margin-right: 4px; }
						.cost-value { color: #1e293b; font-weight: 500; }
						.cost-total { border-top: 1px solid #e2e8f0; margin-top: 6px; padding-top: 6px; font-weight: 600; color: #4f46e5; }
						.table-success td { background-color: #f0fdf4 !important; }
						.table-secondary td { background-color: #f8fafc !important; }
						.pagination-controls { padding: 16px 24px; background: #f8fafc; border-top: 1px solid #f1f5f9; }
						.boq-select-wrapper { position: relative; }
						.boq-select-wrapper select { appearance: none; padding-right: 30px; }
						.boq-select-wrapper::after { content: '\u25BC'; position: absolute; right: 10px; top: 12px; font-size: 10px; color: #94a3b8; pointer-events: none; }
						.site-area-scroll { display: flex; gap: 8px; overflow-x: auto; padding-bottom: 4px; }
						.site-area-scroll .form-control { min-width: 140px; }
						.site-area-scroll .area-input { min-width: 90px; max-width: 120px; }
						.cost-remarks-stack { display: flex; flex-direction: column; gap: 8px; }
						.footer-totals { background: #f8fafc; }
						.footer-totals tr:first-child td { border-top: 2px solid #e2e8f0; }
						.day-total-row { color: #4f46e5; font-size: 14px; }
						.page-total-row { color: #64748b; font-size: 12px; }
						.dpr-table-container { overflow-x: auto; }
						.table { min-width: 980px; }
						@media (max-width: 992px) {
							.filters-card .row { gap: 8px; }
							.filters-card .col-md-2,
							.filters-card .col-md-3,
							.filters-card .col-md-5 { flex: 0 0 100%; max-width: 100%; }
							.filters-card .text-right { justify-content: flex-start; flex-wrap: wrap; }
							.pagination-controls { flex-wrap: wrap; gap: 8px; }
							.pagination-controls .d-flex { flex-wrap: wrap; gap: 8px; }
						}
						@media (max-width: 768px) {
							.table { min-width: 880px; }
							.cost-card { padding: 8px; }
							.site-area-scroll .form-control { min-width: 120px; }
						}
					</style>

					<div class="filters-card">
							<div class="row align-items-end">
								<div class="col-md-2 compact-link">
									<div id="company-field-wrapper"></div>
								</div>
								<div class="col-md-3 compact-link">
									<div id="project-field-wrapper"></div>
								</div>
								<div class="col-md-2">
									<input type="date" class="form-control compact-date" v-model="date">
								</div>
								<div class="col-md-5 text-right d-flex justify-content-end gap-2 align-items-center flex-wrap">
									<button class="btn btn-outline-secondary btn-sm px-3" @click="showHelpVideo" title="${__('Watch how to create DPR')}">
										<i class="fa fa-play-circle mr-1"></i> ${__('How To')}
									</button>
									<button class="btn btn-outline-secondary btn-sm px-3" @click="showAddSiteDialog()" :disabled="!project">
										<i class="fa fa-map-marker mr-1"></i> ${__('Add Site')}
									</button>
									<button class="btn btn-secondary-modern btn-sm px-3" @click="addRow">
										<i class="fa fa-plus mr-1"></i> Add Row
									</button>
									<button class="btn btn-outline-danger btn-sm px-3" @click="deleteSelected" :disabled="!hasDraftSelection">
										<i class="fa fa-trash mr-1"></i> Delete Selected
									</button>
									<button class="btn btn-primary-modern btn-sm px-4" @click="save(false)">
										<i class="fa fa-save mr-1"></i> Save
									</button>
									<button class="btn btn-info btn-sm px-4" @click="save(true)" :disabled="!hasDraftSelection">
										<i class="fa fa-check-circle mr-1"></i> Submit Selected
									</button>
									<button class="btn btn-outline-danger btn-sm px-3" @click="cancelSelected" :disabled="!hasSubmittedSelection">
										<i class="fa fa-ban mr-1"></i> Cancel Selected
									</button>
								</div>
							</div>
					</div>

                    <div v-if="loading" class="text-center p-5">
						<div class="spinner-border text-primary mb-3" role="status"></div>
						<p class="text-muted">Loading data...</p>
					</div>
					<div v-else class="dpr-table-container">
						<table class="table mb-0">
							<thead>
								<tr>
                                    <th style="width: 40px" class="text-center p-3">
                                        <input type="checkbox" v-model="allSelected">
                                    </th>
									<th class="p-3 text-muted small text-uppercase" style="width: 15%;">BOQ Item</th>
									<th class="p-3 text-muted small text-uppercase" style="width: 16%;">Site & Area</th>
									<th class="p-3 text-muted small text-uppercase" style="width: 32%;">Labour, Materials & Overheads</th>
									<th class="p-3 text-muted small text-uppercase" style="width: 22%;">Costs & Remarks</th>
									<th class="p-3 text-muted small text-uppercase text-center" style="width: 8%;">Actions</th>
								</tr>
							</thead>
							<tbody>
								<tr v-for="(row, idx) in paginatedRows" :key="idx" :class="{'table-success': row.docstatus == 1, 'table-secondary': row.docstatus == 2}">
                                    <td class="text-center">
                                        <input type="checkbox" v-model="row.selected">
                                    </td>
									<td>
										<div class="boq-select-wrapper mb-2">
											<label class="small text-muted mb-1">BOQ Item <span class="text-danger font-weight-bold">*</span></label>
                                        	<select class="form-control" v-model="row.boq_item" :disabled="row.docstatus > 0" :class="{'border-danger': !row.boq_item && row.docstatus === 0}">
                                            	<option value="">Select BOQ Item</option>
                                            	<option v-for="item in masterData.boq_items" :key="item.name" :value="item.name">
                                                	{{ item.item_code }} - {{ item.description }}
                                            	</option>
                                        	</select>
										</div>
                                        <div class="text-muted small px-1" v-if="row.boq_item">
                                            <i class="fa fa-info-circle mr-1"></i>
											Balance: <strong>{{ getAvailableBalance(row.boq_item).toFixed(2) }}</strong> {{ boqItemsMap[row.boq_item]?.unit }}
                                        </div>
										<div v-if="row.name" class="mt-2 px-1">
											<a :href="'/app/daily-progress-record/' + row.name" target="_blank" class="badge badge-light text-primary border">
												<i class="fa fa-link mr-1"></i>{{ row.name }}
											</a>
										</div>
                                    </td>
									<td>
										<label class="small text-muted mb-1">Site <span class="text-danger font-weight-bold">*</span></label>
										<div class="site-area-scroll" style="display: flex;gap: 10px; flex-direction: column;">
											<div class="d-flex gap-1 align-items-center">
											 <select class="form-control" v-model="row.site" :disabled="row.docstatus > 0" :class="{'border-danger': !row.site && row.docstatus === 0}">
												<option value="">Select Site</option>
												<option v-for="site in masterData.sites" :key="site.name" :value="site.name">
													{{ site.site_name || site.name }}
												</option>
											</select>
											<button class="btn btn-outline-secondary btn-xs px-2" @click="showAddSiteDialog(idx)" :disabled="!project || row.docstatus > 0" title="${__('Add new site')}">+</button>
											</div>
											<div>
											<label>Area : </label>
											<input type="number" class="form-control text-center area-input" v-model.number="row.area_covered" step="0.01" :disabled="row.docstatus > 0" placeholder="Area">
											</div>
										</div>
                                    </td>
									<td>
										<div class="row">
											<div class="col-md-12 mb-2">
												<div class="d-flex align-items-center gap-2 mb-1">
													<label class="small text-muted mb-0">Employees</label>
													<button class="btn btn-outline-secondary btn-xs px-2 py-0" @click="fetchFromRoster(idx)" :disabled="!project || !date || row.docstatus > 0" title="Fetch from Daily Roster">
														<i class="fa fa-download"></i> Fetch from Roster
													</button>
												</div>
												<SimpleMultiselect 
													:options="masterData.employees" 
													v-model="row.employees"
													label-field="employee_name"
													value-field="name"
													placeholder="Add Employees"
													:disabled="row.docstatus > 0"
												/>
											</div>
											<div class="col-md-12 mb-2">
												<label class="small text-muted mb-1">Absent (Reference)</label>
												<SimpleMultiselect 
													:options="absentEmployeeOptions"
													v-model="row.absent_employees"
													label-field="employee_name"
													value-field="name"
													placeholder="Add Absent Employees"
													:disabled="row.docstatus > 0"
												/>
											</div>
											<div class="col-md-6">
												<label class="small text-muted mb-1">Materials</label>
												<SimpleMultiselect 
													:options="computedMaterialOptions" 
													v-model="row.materials"
													label-field="display_label"
													value-field="name"
													:with-quantity="true"
													:rate-field="'rate'"
													placeholder="Add Materials"
													:disabled="row.docstatus > 0"
												/>
											</div>
											<div class="col-md-6">
												<label class="small text-muted mb-1">Overheads</label>
												<SimpleMultiselect 
													:options="masterData.overhead_accounts" 
													v-model="row.overheads"
													label-field="display_label"
													value-field="name"
													:with-quantity="true"
													prompt-label="Amount"
													placeholder="Add Overheads"
													:disabled="row.docstatus > 0"
												/>
											</div>
										</div>
                                    </td>
                                    <td>
										<div class="small mb-1" style="visibility: hidden;">&nbsp;</div>
										<div class="cost-remarks-stack" style="display: flex; flex-direction: column; gap: 8px;">
											<div class="cost-card border">
												<div v-if="row.labour_cost"><span class="cost-label">Labour:</span><span class="cost-value">{{ showCosts ? row.labour_cost.toFixed(2) : 'XX' }}</span></div>
												<div v-if="row.material_cost"><span class="cost-label">Material:</span><span class="cost-value">{{ showCosts ? row.material_cost.toFixed(2) : 'XX' }}</span></div>
												<div v-if="row.asset_cost"><span class="cost-label">Asset:</span><span class="cost-value">{{ showCosts ? row.asset_cost.toFixed(2) : 'XX' }}</span></div>
												<div v-if="row.overhead_cost"><span class="cost-label">Overhead:</span><span class="cost-value">{{ showCosts ? row.overhead_cost.toFixed(2) : 'XX' }}</span></div>
												<div class="cost-total" v-if="row.total_cost">Total: {{ showCosts ? row.total_cost.toFixed(2) : 'XX' }}</div>
											</div>
											<div>
											<label>Remarks: </label>
											<textarea class="form-control form-control-sm" v-model="row.remarks" rows="2" placeholder="Enter remarks..."></textarea>
											</div>
										</div>
                                    </td>
									<td class="text-center">
										<div class="d-flex flex-column gap-2 align-items-center">
											<a v-if="row.name" :href="'/app/daily-progress-record/' + row.name" target="_blank" class="btn btn-outline-secondary btn-sm" title="View Detail">
												<i class="fa fa-external-link"></i>
											</a>
                                        	<button v-if="row.docstatus === 0" class="btn btn-outline-danger btn-sm" @click="removeRow(idx)" title="${__('Delete row')}">
                                            	<i class="fa fa-trash mr-1"></i>${__('Delete')}
                                        	</button>
										</div>
                                    </td>
								</tr>
							</tbody>
							<tfoot class="footer-totals">
								<tr class="day-total-row">
									<td colspan="6" class="p-3">
										<div class="d-flex flex-wrap justify-content-between align-items-center gap-2">
											<div class="font-weight-bold">Day Totals (All Pages):</div>
											<div class="text-muted small">
												L: <span class="cost-value">{{ showCosts ? (masterData.day_totals?.labour_cost || 0).toFixed(2) : 'XX' }}</span>
												| M: <span class="cost-value">{{ showCosts ? (masterData.day_totals?.material_cost || 0).toFixed(2) : 'XX' }}</span>
												| O: <span class="cost-value">{{ showCosts ? (masterData.day_totals?.overhead_cost || 0).toFixed(2) : 'XX' }}</span>
												| Total: <span class="cost-total">{{ showCosts ? (masterData.day_totals?.total_cost || 0).toFixed(2) : 'XX' }}</span>
											</div>
											<div class="text-muted small">
												Page Totals: L {{ showCosts ? summaryTotals.labour.toFixed(2) : 'XX' }} | M {{ showCosts ? summaryTotals.material.toFixed(2) : 'XX' }} | O {{ showCosts ? summaryTotals.overhead.toFixed(2) : 'XX' }} | Total {{ showCosts ? summaryTotals.total.toFixed(2) : 'XX' }}
											</div>
										</div>
									</td>
								</tr>
							</tfoot>
						</table>
						
						<!-- Pagination -->
						<div class="pagination-controls d-flex justify-content-between align-items-center">
							<div class="text-muted small">
								Showing <strong>{{ paginatedRows.length }}</strong> of <strong>{{ totalRows }}</strong> records
							</div>
							<div class="d-flex align-items-center gap-3">
								<div class="d-flex align-items-center">
									<span class="text-muted small mr-2">Page size</span>
									<select class="form-control form-control-sm" v-model.number="pageSize" @change="changePageSize">
										<option v-for="size in pageSizeOptions" :key="size" :value="size">{{ size }}</option>
									</select>
								</div>
								<button class="btn btn-secondary-modern btn-sm px-3" :disabled="currentPage == 1" @click="changePage(currentPage - 1)">
									<i class="fa fa-chevron-left mr-1"></i> Previous
								</button>
								<span class="font-weight-bold small">Page {{ currentPage }} of {{ totalPages }}</span>
								<button class="btn btn-secondary-modern btn-sm px-3" :disabled="currentPage == totalPages" @click="changePage(currentPage + 1)">
									Next <i class="fa fa-chevron-right ml-1"></i>
								</button>
							</div>
						</div>
					</div>
				</div>
			`
		};

		// Simple Multiselect Component
		const SimpleMultiselect = {
			props: ['options', 'modelValue', 'labelField', 'valueField', 'placeholder', 'withQuantity', 'promptLabel', 'rateField', 'disabled'],
			emits: ['update:modelValue'],
			setup(props, { emit }) {
				const isOpen = ref(false);
				const searchQuery = ref('');
				const searchInput = ref(null);
				const rootEl = ref(null);
				const showCosts = ref((frappe.user_roles || []).some(r => ['Purchase Manager', 'Accounts Manager', 'Accounts User'].includes(r)));

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
					const model = props.modelValue || [];
					return model.map(item => {
						const val = typeof item === 'object' ? item[props.valueField] : item;
						const opt = props.options.find(o => o[props.valueField] === val);
						return {
							...item,
							[props.valueField]: val,
							[props.labelField]: opt ? opt[props.labelField] : (item[props.labelField] || val),
							qty: item.qty || (item.hours !== undefined ? item.hours : null)
						};
					});
				});

				const toggle = () => {
					if (props.disabled) return;
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
					const current = [...(props.modelValue || [])].map(i => typeof i === 'object' ? i : { [props.valueField]: i });

					if (current.some(i => i[props.valueField] === opt[props.valueField])) {
						frappe.msgprint("Already added.");
						return;
					}

					isOpen.value = false;

					if (props.withQuantity || opt.rate_per_day !== undefined) {
						const isEmployee = opt.rate_per_day !== undefined;
						const label = isEmployee ? 'Hours' : (props.promptLabel || 'Quantity');
						const defaultValue = isEmployee ? 8 : 1;

						const fields = [
							{
								label: label,
								fieldname: 'val',
								fieldtype: 'Float',
								reqd: 1,
								default: defaultValue
							},
							{
								label: 'Remarks/Description',
								fieldname: 'remark',
								fieldtype: 'Small Text'
							}
						];

						frappe.prompt(fields, (values) => {
							const parsedVal = parseFloat(values.val);
							if (isNaN(parsedVal) || parsedVal <= 0) {
								frappe.msgprint("Invalid value");
								return;
							}

							const newItem = {
								[props.valueField]: opt[props.valueField]
							};

							if (isEmployee) {
								newItem.employee = opt[props.valueField];
								newItem.name = opt[props.valueField]; // for multiselect
								newItem.hours = parsedVal;
								newItem.rate_per_day = opt.rate_per_day;
								newItem.amount = opt.rate_per_day * (parsedVal / 8);
								newItem.remarks = values.remark || "";
							} else if (opt.valuation_rate !== undefined) {
								// Material
								newItem.item_code = opt[props.valueField];
								newItem.name = opt[props.valueField]; // for multiselect
								newItem.qty = parsedVal;
								newItem.rate = opt.valuation_rate || 0;
								newItem.amount = newItem.rate * parsedVal;
								newItem.description = values.remark || "";
							} else {
								// Overhead
								newItem.account = opt[props.valueField];
								newItem.name = opt[props.valueField]; // for multiselect
								newItem.amount = parsedVal;
								newItem.description = values.remark || "";
							}

							current.push(newItem);
							emit('update:modelValue', current);
						}, `Enter Details for ${opt[props.labelField]}`, 'Add');

						return;
					}

					current.push({ [props.valueField]: opt[props.valueField] });
					emit('update:modelValue', current);
				};

				const remove = (val) => {
					const current = (props.modelValue || []).filter(v => {
						const vVal = typeof v === 'object' ? v[props.valueField] : v;
						return vVal !== val;
					});
					emit('update:modelValue', current);
				};

				return { isOpen, selectedItems, toggle, select, remove, searchQuery, filteredOptions, searchInput, rootEl, showCosts };
			},
			template: `
				<div class="simple-multiselect position-relative" ref="rootEl">
					<div class="multiselect-input form-control input-sm" @click="toggle" :class="{'bg-light': disabled}" style="height: auto; min-height: 30px; cursor: pointer;">
                        <span v-if="!selectedItems.length" class="text-muted">{{ placeholder }}</span>
                        <div v-else class="selected-tags d-flex flex-wrap gap-1">
                            <span v-for="item in selectedItems" :key="item[valueField]" class="badge badge-primary p-1" style="white-space: normal; text-align: left; font-weight: normal;">
                                {{ item[labelField] }}
                                <span v-if="item.qty !== null" class="ml-1 font-weight-bold">({{ item.qty }})</span>
                                <span v-if="!disabled" class="ml-1 cursor-pointer font-weight-bold" @click.stop="remove(item[valueField])">&times;</span>
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
							<span v-if="opt.rate_per_day && showCosts" class="text-muted small ml-1">
								(Rate: {{ opt.rate_per_day.toFixed(2) }})
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
