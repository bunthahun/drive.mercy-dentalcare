/**
 * 5TB Cloud Storage - Web Application Logic
 */

let currentCategory = "buntha";
let currentSearch = "";
let currentView = localStorage.getItem("win11_view_mode") || "details";
let currentLang = "km";
let filesData = [];
let foldersData = [];
let currentFolderId = null;
let folderStack = [];
let activeContextItem = null;
let selectedFileIds = new Set();
let selectedFolderIds = new Set();
let currentSortCol = "name";
let currentSortDir = "asc";
let navHistory = [{ folderId: null, stack: [] }];
let historyIndex = 0;
let isInternalDragging = false;

// Localization dictionaries
const i18n = {
    km: {
        all_files: "ឯកសារទាំងអស់",
        documents: "ឯកសារអត្ថបទ",
        images: "រូបភាព",
        videos: "វីដេអូ",
        music: "តន្ត្រី / សំឡេង",
        archives: "ឯកសារបង្ហាប់",
        favorites: "សំណព្វចិត្ត",
        trash: "ធុងសំរាម",
        quota_title: "⚡ ទំហំផ្ទុកទិន្នន័យ Cloud",
        quota_free: "នៅសល់",
        upload_file: "ផ្ទុកឯកសារឡើង",
        empty_trash: "សម្អាតធុងសំរាម",
        search_placeholder: "ស្វែងរកឯកសារតាមឈ្មោះ...",
        drop_hint: "ទម្លាក់ឯកសារនៅទីនេះដើម្បីផ្ទុកឡើង",
        no_files: "មិនទាន់មានឯកសារនៅឡើយទេ",
        connected: "Mercy Dental Care",
        offline: "Mercy Dental Care",
        download: "ទាញយក",
        delete: "លុប",
        restore: "ស្តារឡើងវិញ",
        permanent: "លុបអចិន្ត្រៃយ៍",
        lang_btn: "🇰🇭 ភាសាខ្មែរ"
    },
    en: {
        all_files: "All Files",
        documents: "Documents",
        images: "Photos & Images",
        videos: "Videos",
        music: "Music & Audio",
        archives: "Archives (ZIP/RAR)",
        favorites: "Favorites",
        trash: "Recycle Bin",
        quota_title: "⚡ Cloud Storage Quota",
        quota_free: "Free",
        upload_file: "Upload File",
        empty_trash: "Empty Trash",
        search_placeholder: "Search files by name...",
        drop_hint: "Drop files here to upload",
        no_files: "No files found",
        connected: "Mercy Dental Care",
        offline: "Mercy Dental Care",
        download: "Download",
        delete: "Delete",
        restore: "Restore",
        permanent: "Delete Permanently",
        lang_btn: "🇺🇸 English"
    }
};

document.addEventListener("DOMContentLoaded", () => {
    initAuthSecurity();
    initEventListeners();
    initContextMenuListeners();
    initMarqueeSelection();
    updateCurrentDriveHeader();
    updateAdminVisibility();
    fetchStats();
    loadFiles();
});

function isAdminUser() {
    return sessionStorage.getItem("is_admin") === "true" || localStorage.getItem("is_admin") === "true";
}

function updateAdminVisibility() {
    const btnSettings = document.getElementById("btnSettingsOpen");
    if (btnSettings) {
        btnSettings.style.display = isAdminUser() ? "inline-flex" : "none";
    }
}

function normalizeKhmerInput(str) {
    if (!str) return "";
    const khmerDigits = ["០","១","២","៣","៤","៥","៦","៧","៨","៩"];
    let res = String(str);
    khmerDigits.forEach((kd, idx) => {
        res = res.replaceAll(kd, idx.toString());
    });
    return res.replace(/[\u200B-\u200D\uFEFF\u00A0\s]/g, "");
}

function initAuthSecurity() {
    const lockScreen = document.getElementById("siteLockScreen");
    const lockInput = document.getElementById("siteLockInput");
    const lockBtn = document.getElementById("btnSiteUnlock");
    const lockToggleBtn = document.getElementById("btnToggleSitePwd");
    const lockError = document.getElementById("siteLockError");
    const lockCard = document.getElementById("lockCardBox");
    const btnLogout = document.getElementById("btnLogoutSite");

    const isSiteAuth = sessionStorage.getItem("site_authenticated") === "true" || localStorage.getItem("site_authenticated") === "true";
    if (isSiteAuth) {
        if (lockScreen) {
            lockScreen.classList.add("unlocked");
            lockScreen.style.display = "none";
        }
    } else {
        if (lockScreen) {
            lockScreen.classList.remove("unlocked");
            lockScreen.style.display = "flex";
            if (lockInput) setTimeout(() => lockInput.focus(), 150);
        }
    }

    if (lockToggleBtn && lockInput) {
        lockToggleBtn.addEventListener("click", () => {
            if (lockInput.type === "password") {
                lockInput.type = "text";
                lockToggleBtn.textContent = "🙈";
                lockToggleBtn.title = "លាក់លេខសម្ងាត់";
            } else {
                lockInput.type = "password";
                lockToggleBtn.textContent = "👁️";
                lockToggleBtn.title = "បង្ហាញលេខសម្ងាត់";
            }
        });
    }

    async function attemptSiteUnlock() {
        const rawPwd = lockInput ? lockInput.value : "";
        const pwd = normalizeKhmerInput(rawPwd);
        if (!pwd) {
            if (lockError) lockError.textContent = "សូមបញ្ចូលលេខសម្ងាត់! (Enter password)";
            if (lockCard) {
                lockCard.classList.add("shake");
                setTimeout(() => lockCard.classList.remove("shake"), 450);
            }
            return;
        }

        try {
            const res = await fetch("/api/auth/verify-site", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ password: pwd })
            });
            const data = await res.json();
            if (data.success) {
                sessionStorage.setItem("site_authenticated", "true");
                localStorage.setItem("site_authenticated", "true");
                if (data.is_admin || data.is_master) {
                    sessionStorage.setItem("is_admin", "true");
                    localStorage.setItem("is_admin", "true");
                } else {
                    sessionStorage.removeItem("is_admin");
                    localStorage.removeItem("is_admin");
                }
                updateAdminVisibility();

                if (data.unlocked_drives && Array.isArray(data.unlocked_drives)) {
                    data.unlocked_drives.forEach(d => {
                        sessionStorage.setItem("unlocked_drive_" + d, "true");
                        localStorage.setItem("unlocked_drive_" + d, "true");
                    });
                }
                if (data.default_drive) {
                    currentCategory = data.default_drive;
                    updateCurrentDriveHeader();
                }
                if (lockError) lockError.textContent = "";
                if (lockScreen) {
                    lockScreen.classList.add("unlocked");
                    setTimeout(() => lockScreen.style.display = "none", 400);
                }
                fetchStats();
                loadFiles();
            } else {
                if (lockError) lockError.textContent = "លេខសម្ងាត់មិនត្រឹមត្រូវទេ! (Incorrect password)";
                if (lockCard) {
                    lockCard.classList.add("shake");
                    setTimeout(() => lockCard.classList.remove("shake"), 450);
                }
                if (lockInput) lockInput.select();
            }
        } catch (e) {
            if (lockError) lockError.textContent = "Error: " + e.message;
        }
    }

    if (lockBtn) lockBtn.addEventListener("click", attemptSiteUnlock);
    if (lockInput) lockInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") attemptSiteUnlock();
    });

    if (btnLogout) {
        btnLogout.addEventListener("click", () => {
            sessionStorage.removeItem("site_authenticated");
            sessionStorage.removeItem("unlocked_drive_buntha");
            sessionStorage.removeItem("unlocked_drive_vuochlin");
            sessionStorage.removeItem("unlocked_drive_mercy");
            sessionStorage.removeItem("is_admin");
            localStorage.removeItem("site_authenticated");
            localStorage.removeItem("unlocked_drive_buntha");
            localStorage.removeItem("unlocked_drive_vuochlin");
            localStorage.removeItem("unlocked_drive_mercy");
            localStorage.removeItem("is_admin");
            updateAdminVisibility();
            if (lockInput) lockInput.value = "";
            if (lockError) lockError.textContent = "";
            if (lockScreen) {
                lockScreen.classList.remove("unlocked");
                lockScreen.style.display = "flex";
                if (lockInput) setTimeout(() => lockInput.focus(), 150);
            }
        });
    }
}

function requestDriveAccess(driveKey, onUnlocked) {
    if (driveKey === "trash") {
        onUnlocked();
        return;
    }

    const isUnlocked = sessionStorage.getItem("unlocked_drive_" + driveKey) === "true" ||
                       localStorage.getItem("unlocked_drive_" + driveKey) === "true";
    if (isUnlocked) {
        onUnlocked();
        return;
    }

    const driveNames = {
        buntha: "HUN BUNTHA",
        vuochlin: "NEANG VUOCHLIN",
        mercy: "Mercy Dental Care"
    };
    const driveName = driveNames[driveKey] || driveKey;

    const modal = document.getElementById("drivePasswordModal");
    const titleEl = document.getElementById("drivePwdTitle");
    const promptEl = document.getElementById("drivePwdPrompt");
    const inputEl = document.getElementById("inputDrivePwd");
    const toggleBtn = document.getElementById("btnToggleDrivePwd");
    const errorEl = document.getElementById("drivePwdError");
    const confirmBtn = document.getElementById("btnConfirmDrivePwd");
    const cancelBtn = document.getElementById("btnCancelDrivePwd");
    const closeBtn = document.getElementById("btnCloseDrivePwd");

    if (titleEl) titleEl.textContent = `🔒 សោសុវត្ថិភាព Drive [${driveName}]`;
    if (promptEl) promptEl.textContent = `សូមបញ្ចូលលេខកូដសម្ងាត់ (Password) ដើម្បីបើកមើល Drive [${driveName}]៖`;
    if (inputEl) {
        inputEl.value = "";
        inputEl.type = "password";
        if (toggleBtn) toggleBtn.textContent = "👁️";
        setTimeout(() => inputEl.focus(), 100);
    }
    if (errorEl) errorEl.textContent = "";

    if (modal) modal.style.display = "flex";

    const cleanup = () => {
        if (confirmBtn) confirmBtn.onclick = null;
        if (cancelBtn) cancelBtn.onclick = null;
        if (closeBtn) closeBtn.onclick = null;
        if (inputEl) inputEl.onkeydown = null;
        if (toggleBtn) toggleBtn.onclick = null;
        if (modal) modal.style.display = "none";
    };

    const handleCancel = () => {
        cleanup();
    };

    if (toggleBtn && inputEl) {
        toggleBtn.onclick = () => {
            if (inputEl.type === "password") {
                inputEl.type = "text";
                toggleBtn.textContent = "🙈";
                toggleBtn.title = "លាក់លេខសម្ងាត់";
            } else {
                inputEl.type = "password";
                toggleBtn.textContent = "👁️";
                toggleBtn.title = "បង្ហាញលេខសម្ងាត់";
            }
        };
    }

    const handleConfirm = async () => {
        const rawPwd = inputEl ? inputEl.value : "";
        const pwd = normalizeKhmerInput(rawPwd);
        if (!pwd) {
            if (errorEl) errorEl.textContent = "សូមបញ្ចូលលេខកូដសម្ងាត់ Drive!";
            if (inputEl) inputEl.focus();
            return;
        }

        if (confirmBtn) {
            confirmBtn.disabled = true;
            confirmBtn.textContent = "កំពុងផ្ទៀងផ្ទាត់...";
        }

        try {
            const res = await fetch("/api/auth/verify-drive", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ drive: driveKey, password: pwd })
            });
            const data = await res.json();
            if (data.success) {
                sessionStorage.setItem("unlocked_drive_" + driveKey, "true");
                localStorage.setItem("unlocked_drive_" + driveKey, "true");
                cleanup();
                onUnlocked();
            } else {
                if (confirmBtn) {
                    confirmBtn.disabled = false;
                    confirmBtn.textContent = "បើកមើល (Unlock)";
                }
                if (errorEl) errorEl.textContent = "លេខកូដសម្ងាត់មិនត្រឹមត្រូវទេ! (Incorrect drive password)";
                if (inputEl) {
                    inputEl.classList.add("shake");
                    setTimeout(() => inputEl.classList.remove("shake"), 450);
                    inputEl.select();
                }
            }
        } catch (e) {
            if (confirmBtn) {
                confirmBtn.disabled = false;
                confirmBtn.textContent = "បើកមើល (Unlock)";
            }
            if (errorEl) errorEl.textContent = "Error: " + e.message;
        }
    };

    const handleKey = (e) => {
        if (e.key === "Enter") handleConfirm();
        else if (e.key === "Escape") handleCancel();
    };

    if (confirmBtn) confirmBtn.onclick = handleConfirm;
    if (cancelBtn) cancelBtn.onclick = handleCancel;
    if (closeBtn) closeBtn.onclick = handleCancel;
    if (inputEl) inputEl.onkeydown = handleKey;
}

function initEventListeners() {
    // Windows 11 Tabs & Sidebar Drive Switching Logic
    const tabBuntha = document.getElementById("tabBuntha");
    const tabVuochlin = document.getElementById("tabVuochlin");
    const tabMercy = document.getElementById("tabMercy");
    const btnTabNew = document.getElementById("btnTabNew");

    function switchDrive(driveKey) {
        requestDriveAccess(driveKey, () => {
            currentCategory = driveKey;
            currentFolderId = null;
            folderStack = [];
            navHistory = [{ folderId: null, stack: [] }];
            historyIndex = 0;
            clearSelection();

            // Update sidebar
            document.querySelectorAll(".nav-item").forEach(b => {
                b.classList.toggle("active", b.dataset.cat === driveKey);
            });

            // Update tabs
            if (tabBuntha) tabBuntha.classList.toggle("active", driveKey === "buntha");
            if (tabVuochlin) tabVuochlin.classList.toggle("active", driveKey === "vuochlin");
            if (tabMercy) tabMercy.classList.toggle("active", driveKey === "mercy");

            updateCurrentDriveHeader();
            loadFiles();
        });
    }

    if (tabBuntha) tabBuntha.addEventListener("click", () => switchDrive("buntha"));
    if (tabVuochlin) tabVuochlin.addEventListener("click", () => switchDrive("vuochlin"));
    if (tabMercy) tabMercy.addEventListener("click", () => switchDrive("mercy"));

    if (btnTabNew) btnTabNew.addEventListener("click", () => {
        const order = ["buntha", "vuochlin", "mercy"];
        const curIdx = order.indexOf(currentCategory);
        const nextDrive = order[(curIdx + 1) % order.length];
        switchDrive(nextDrive);
    });

    // Nav items (Sidebar)
    document.querySelectorAll(".nav-item").forEach(btn => {
        btn.addEventListener("click", () => {
            const cat = btn.dataset.cat;
            switchDrive(cat);
        });
    });

    // Select All Button
    const btnSelectAll = document.getElementById("btnToggleSelectAll");
    if (btnSelectAll) {
        btnSelectAll.addEventListener("click", () => {
            selectAllFiles();
        });
    }

    // Floating Selection Bar Actions
    const btnSelMove = document.getElementById("btnSelectionMove");
    if (btnSelMove) {
        btnSelMove.addEventListener("click", () => {
            if (selectedFileIds.size > 0 || selectedFolderIds.size > 0) {
                openMoveModal(Array.from(selectedFileIds), Array.from(selectedFolderIds));
            }
        });
    }

    const btnSelDelete = document.getElementById("btnSelectionDelete");
    if (btnSelDelete) {
        btnSelDelete.addEventListener("click", () => {
            deleteSelectedFiles();
        });
    }

    const btnSelClear = document.getElementById("btnSelectionClear");
    if (btnSelClear) {
        btnSelClear.addEventListener("click", () => {
            clearSelection();
        });
    }

    // Move Modal Close Actions
    const moveModal = document.getElementById("moveModal");
    const btnCloseMove = document.getElementById("btnCloseMoveModal");
    const btnCancelMove = document.getElementById("btnCancelMove");
    if (btnCloseMove) btnCloseMove.addEventListener("click", () => { if (moveModal) moveModal.style.display = "none"; });
    if (btnCancelMove) btnCancelMove.addEventListener("click", () => { if (moveModal) moveModal.style.display = "none"; });
    if (moveModal) {
        moveModal.addEventListener("click", (e) => {
            if (e.target === moveModal) moveModal.style.display = "none";
        });
    }

    // Context Menu: Move to Folder
    const filecmenuMove = document.getElementById("filecmenuMove");
    if (filecmenuMove) {
        filecmenuMove.addEventListener("click", () => {
            hideAllContextMenus();
            if (activeContextItem && activeContextItem.type === "file") {
                const targetIds = selectedFileIds.has(activeContextItem.id) && selectedFileIds.size > 1
                    ? Array.from(selectedFileIds)
                    : [activeContextItem.id];
                openMoveModal(targetIds);
            }
        });
    }

    // Preview Modal Close
    const previewModal = document.getElementById("previewModal");
    const closePreviewBtn = document.getElementById("btnClosePreview");
    if (closePreviewBtn) {
        closePreviewBtn.addEventListener("click", () => {
            if (previewModal) previewModal.style.display = "none";
            const body = document.getElementById("previewModalBody");
            if (body) body.innerHTML = "";
        });
    }
    if (previewModal) {
        previewModal.addEventListener("click", (e) => {
            if (e.target === previewModal) {
                previewModal.style.display = "none";
                const body = document.getElementById("previewModalBody");
                if (body) body.innerHTML = "";
            }
        });
    }

    // Language Toggle
    document.getElementById("btnLangToggle").addEventListener("click", () => {
        currentLang = currentLang === "km" ? "en" : "km";
        applyLanguage();
    });

    // Windows 11 Ribbon Dropdowns Toggle Logic
    const initDropdown = (btnId, menuId) => {
        const btn = document.getElementById(btnId);
        const menu = document.getElementById(menuId);
        if (btn && menu) {
            btn.addEventListener("click", (e) => {
                e.stopPropagation();
                const isShowing = menu.style.display === "block";
                closeAllRibbonDropdowns();
                if (!isShowing) {
                    menu.style.display = "block";
                    btn.classList.add("active");
                }
            });
        }
    };
    initDropdown("btnWinNew", "menuWinNew");
    initDropdown("btnWinSort", "menuWinSort");
    initDropdown("btnWinView", "menuWinView");
    initDropdown("btnWinMore", "menuWinMore");

    window.addEventListener("click", () => {
        closeAllRibbonDropdowns();
    });

    // Windows 11 Ribbon 'New' Dropdown Actions
    const btnMenuNewFolder = document.getElementById("btnMenuNewFolder");
    if (btnMenuNewFolder) {
        btnMenuNewFolder.addEventListener("click", () => {
            closeAllRibbonDropdowns();
            promptNewFolder();
        });
    }

    const btnMenuUploadFile = document.getElementById("btnMenuUploadFile");
    if (btnMenuUploadFile) {
        btnMenuUploadFile.addEventListener("click", () => {
            closeAllRibbonDropdowns();
            const fi = document.getElementById("fileInput");
            if (fi) fi.click();
        });
    }

    // Windows 11 Ribbon Actions: Cut, Copy, Rename, Delete
    const btnRibbonCut = document.getElementById("btnRibbonCut");
    if (btnRibbonCut) {
        btnRibbonCut.addEventListener("click", () => {
            if (selectedFileIds.size > 0 || selectedFolderIds.size > 0) {
                openMoveModal(Array.from(selectedFileIds), Array.from(selectedFolderIds));
            }
        });
    }

    const btnRibbonCopy = document.getElementById("btnRibbonCopy");
    if (btnRibbonCopy) {
        btnRibbonCopy.addEventListener("click", () => {
            if (selectedFileIds.size > 0) {
                const names = filesData.filter(f => selectedFileIds.has(f.id)).map(f => f.file_name).join(String.fromCharCode(10));
                navigator.clipboard.writeText(names);
            }
        });
    }

    const btnRibbonRename = document.getElementById("btnRibbonRename");
    if (btnRibbonRename) {
        btnRibbonRename.addEventListener("click", () => {
            if (selectedFolderIds.size === 1) {
                const folderId = Array.from(selectedFolderIds)[0];
                const folder = foldersData.find(f => f.id === folderId);
                if (folder) promptRenameFolder(folder.id, folder.folder_name);
            } else if (selectedFileIds.size === 1) {
                const fileId = Array.from(selectedFileIds)[0];
                const file = filesData.find(f => f.id === fileId);
                if (file) promptRenameFile(file.id, file.file_name);
            }
        });
    }

    const btnRibbonDelete = document.getElementById("btnRibbonDelete");
    if (btnRibbonDelete) {
        btnRibbonDelete.addEventListener("click", () => {
            deleteSelectedFiles();
        });
    }

    // Windows 11 Ribbon 'Sort' Dropdown Items
    document.querySelectorAll("#menuWinSort [data-sort]").forEach(item => {
        item.addEventListener("click", () => {
            closeAllRibbonDropdowns();
            setSort(item.dataset.sort);
        });
    });

    document.querySelectorAll("#menuWinSort [data-order]").forEach(item => {
        item.addEventListener("click", () => {
            closeAllRibbonDropdowns();
            setOrder(item.dataset.order);
        });
    });

    // Windows 11 Ribbon 'View' Dropdown Items (Picture 1)
    document.querySelectorAll("#menuWinView [data-view]").forEach(item => {
        item.addEventListener("click", () => {
            closeAllRibbonDropdowns();
            setViewMode(item.dataset.view);
        });
    });

    // Windows 11 Ribbon 'More' Actions
    const btnMenuSelectAll = document.getElementById("btnMenuSelectAll");
    if (btnMenuSelectAll) {
        btnMenuSelectAll.addEventListener("click", () => {
            closeAllRibbonDropdowns();
            selectAllFiles();
        });
    }

    const btnMenuClearSelection = document.getElementById("btnMenuClearSelection");
    if (btnMenuClearSelection) {
        btnMenuClearSelection.addEventListener("click", () => {
            closeAllRibbonDropdowns();
            clearSelection();
        });
    }

    const btnMenuEmptyTrash = document.getElementById("btnMenuEmptyTrash");
    if (btnMenuEmptyTrash) {
        btnMenuEmptyTrash.addEventListener("click", () => {
            closeAllRibbonDropdowns();
            emptyTrash();
        });
    }

    // Windows 11 Navigation Controls
    const btnNavBack = document.getElementById("btnNavBack");
    if (btnNavBack) btnNavBack.addEventListener("click", navBack);

    const btnNavForward = document.getElementById("btnNavForward");
    if (btnNavForward) btnNavForward.addEventListener("click", navForward);

    const btnNavUp = document.getElementById("btnNavUp");
    if (btnNavUp) btnNavUp.addEventListener("click", navUp);

    // Table Header Click Sorting (Picture 2)
    ["name", "date", "type", "size"].forEach(col => {
        const th = document.getElementById(`thCol${col.charAt(0).toUpperCase() + col.slice(1)}`);
        if (th) {
            th.addEventListener("click", () => {
                toggleSortCol(col);
            });
        }
    });

    // Master Table Checkbox
    const thMasterCheckbox = document.getElementById("thMasterCheckbox");
    if (thMasterCheckbox) {
        thMasterCheckbox.addEventListener("change", (e) => {
            if (e.target.checked) {
                selectedFileIds.clear();
                selectedFolderIds.clear();
                filesData.forEach(f => selectedFileIds.add(f.id));
                foldersData.forEach(f => selectedFolderIds.add(f.id));
            } else {
                clearSelection();
            }
            updateSelectionUI();
        });
    }

    // Search
    const searchInput = document.getElementById("searchInput");
    const searchClear = document.getElementById("searchClear");
    if (searchInput) {
        searchInput.addEventListener("input", (e) => {
            currentSearch = e.target.value.trim();
            if (searchClear) searchClear.style.display = currentSearch ? "block" : "none";
            loadFiles();
        });
    }
    if (searchClear) {
        searchClear.addEventListener("click", () => {
            if (searchInput) searchInput.value = "";
            currentSearch = "";
            searchClear.style.display = "none";
            loadFiles();
        });
    }

    // Refresh
    const btnRefresh = document.getElementById("btnRefresh");
    if (btnRefresh) {
        btnRefresh.addEventListener("click", () => {
            fetchStats();
            loadFiles();
        });
    }

    // Keyboard Shortcuts
    window.addEventListener("keydown", (e) => {
        if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;
        if (e.key === "F5") {
            e.preventDefault();
            fetchStats();
            loadFiles();
        } else if (e.altKey && e.key === "ArrowLeft") {
            e.preventDefault();
            navBack();
        } else if (e.altKey && e.key === "ArrowRight") {
            e.preventDefault();
            navForward();
        } else if ((e.altKey && e.key === "ArrowUp") || e.key === "Backspace") {
            e.preventDefault();
            navUp();
        } else if (e.key === "Delete") {
            deleteSelectedFiles();
        }
    });

    // Upload button & input
    const fileInput = document.getElementById("fileInput");
    document.getElementById("btnUploadFile").addEventListener("click", () => fileInput.click());
    fileInput.addEventListener("change", (e) => {
        if (e.target.files.length > 0) {
            handleFilesUpload(Array.from(e.target.files));
            fileInput.value = "";
        }
    });

    // Drag and Drop with Dual/Triple Drive Targets
    const dropZone = document.getElementById("dropZone");
    const dropOverlay = document.getElementById("dropOverlay");
    const dropBuntha = document.getElementById("dropTargetBuntha");
    const dropVuochlin = document.getElementById("dropTargetVuochlin");
    const dropMercy = document.getElementById("dropTargetMercy");
    const dropActiveHint = document.getElementById("dropActiveDriveHint");

    let dragCounter = 0;

    window.addEventListener("dragenter", (e) => {
        if (isInternalDragging) return;
        const types = e.dataTransfer ? Array.from(e.dataTransfer.types || []) : [];
        if (!types.includes("Files")) return;
        e.preventDefault();
        dragCounter++;
        if (dropActiveHint) {
            let activeName = "HUN BUNTHA";
            if (currentCategory === "vuochlin") activeName = "NEANG VUOCHLIN";
            else if (currentCategory === "mercy") activeName = "Mercy Dental Care";
            dropActiveHint.textContent = activeName;
        }
        if (dropOverlay) dropOverlay.style.display = "flex";
    });

    window.addEventListener("dragleave", (e) => {
        if (isInternalDragging) return;
        e.preventDefault();
        dragCounter--;
        if (dragCounter <= 0) {
            dragCounter = 0;
            if (dropOverlay) dropOverlay.style.display = "none";
        }
    });

    window.addEventListener("dragover", (e) => {
        if (!isInternalDragging) e.preventDefault();
    });

    if (dropBuntha) {
        dropBuntha.addEventListener("dragover", (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropBuntha.classList.add("drag-hover");
        });
        dropBuntha.addEventListener("dragleave", () => dropBuntha.classList.remove("drag-hover"));
        dropBuntha.addEventListener("drop", (e) => {
            e.preventDefault();
            e.stopPropagation();
            dragCounter = 0;
            if (dropOverlay) dropOverlay.style.display = "none";
            dropBuntha.classList.remove("drag-hover");
            if (e.dataTransfer.files.length > 0) {
                handleFilesUpload(Array.from(e.dataTransfer.files), "buntha");
            }
        });
    }

    if (dropVuochlin) {
        dropVuochlin.addEventListener("dragover", (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropVuochlin.classList.add("drag-hover");
        });
        dropVuochlin.addEventListener("dragleave", () => dropVuochlin.classList.remove("drag-hover"));
        dropVuochlin.addEventListener("drop", (e) => {
            e.preventDefault();
            e.stopPropagation();
            dragCounter = 0;
            if (dropOverlay) dropOverlay.style.display = "none";
            dropVuochlin.classList.remove("drag-hover");
            if (e.dataTransfer.files.length > 0) {
                handleFilesUpload(Array.from(e.dataTransfer.files), "vuochlin");
            }
        });
    }

    if (dropMercy) {
        dropMercy.addEventListener("dragover", (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropMercy.classList.add("drag-hover");
        });
        dropMercy.addEventListener("dragleave", () => dropMercy.classList.remove("drag-hover"));
        dropMercy.addEventListener("drop", (e) => {
            e.preventDefault();
            e.stopPropagation();
            dragCounter = 0;
            if (dropOverlay) dropOverlay.style.display = "none";
            dropMercy.classList.remove("drag-hover");
            if (e.dataTransfer.files.length > 0) {
                handleFilesUpload(Array.from(e.dataTransfer.files), "mercy");
            }
        });
    }

    if (dropOverlay) {
        dropOverlay.addEventListener("drop", (e) => {
            e.preventDefault();
            dragCounter = 0;
            dropOverlay.style.display = "none";
            if (dropBuntha) dropBuntha.classList.remove("drag-hover");
            if (dropVuochlin) dropVuochlin.classList.remove("drag-hover");
            if (dropMercy) dropMercy.classList.remove("drag-hover");
            if (e.dataTransfer.files.length > 0) {
                const targetDrive = currentCategory === "vuochlin" ? "vuochlin" : (currentCategory === "mercy" ? "mercy" : "buntha");
                handleFilesUpload(Array.from(e.dataTransfer.files), targetDrive);
            }
        });
    }

    // Sidebar Drive Drag & Drop Support
    const navBuntha = document.getElementById("btnNavBuntha");
    const navVuochlin = document.getElementById("btnNavVuochlin");
    const navMercy = document.getElementById("btnNavMercy");
    if (navBuntha) {
        navBuntha.addEventListener("dragover", (e) => {
            e.preventDefault();
            e.stopPropagation();
            navBuntha.classList.add("drag-hover-sidebar");
        });
        navBuntha.addEventListener("dragleave", () => navBuntha.classList.remove("drag-hover-sidebar"));
        navBuntha.addEventListener("drop", (e) => {
            e.preventDefault();
            e.stopPropagation();
            navBuntha.classList.remove("drag-hover-sidebar");
            dragCounter = 0;
            if (dropOverlay) dropOverlay.style.display = "none";
            if (e.dataTransfer.files.length > 0) {
                handleFilesUpload(Array.from(e.dataTransfer.files), "buntha");
            }
        });
    }
    if (navVuochlin) {
        navVuochlin.addEventListener("dragover", (e) => {
            e.preventDefault();
            e.stopPropagation();
            navVuochlin.classList.add("drag-hover-sidebar");
        });
        navVuochlin.addEventListener("dragleave", () => navVuochlin.classList.remove("drag-hover-sidebar"));
        navVuochlin.addEventListener("drop", (e) => {
            e.preventDefault();
            e.stopPropagation();
            navVuochlin.classList.remove("drag-hover-sidebar");
            dragCounter = 0;
            if (dropOverlay) dropOverlay.style.display = "none";
            if (e.dataTransfer.files.length > 0) {
                handleFilesUpload(Array.from(e.dataTransfer.files), "vuochlin");
            }
        });
    }
    if (navMercy) {
        navMercy.addEventListener("dragover", (e) => {
            e.preventDefault();
            e.stopPropagation();
            navMercy.classList.add("drag-hover-sidebar");
        });
        navMercy.addEventListener("dragleave", () => navMercy.classList.remove("drag-hover-sidebar"));
        navMercy.addEventListener("drop", (e) => {
            e.preventDefault();
            e.stopPropagation();
            navMercy.classList.remove("drag-hover-sidebar");
            dragCounter = 0;
            if (dropOverlay) dropOverlay.style.display = "none";
            if (e.dataTransfer.files.length > 0) {
                handleFilesUpload(Array.from(e.dataTransfer.files), "mercy");
            }
        });
    }

    // Settings Modal (Admin Only)
    const settingsModal = document.getElementById("settingsModal");
    const openSettings = () => {
        if (!isAdminUser()) {
            alert("🔒 មានតែ Admin ប៉ុណ្ណោះដែលអាចចូលមើល និងកែប្រែលេខកូដសម្ងាត់បាន! (Admin only)");
            return;
        }
        fetchSettings();
        if (settingsModal) settingsModal.style.display = "flex";
    };
    const btnSettings = document.getElementById("btnSettingsOpen");
    if (btnSettings) btnSettings.addEventListener("click", openSettings);
    const btnCloseSettings = document.getElementById("btnCloseSettings");
    if (btnCloseSettings) btnCloseSettings.addEventListener("click", () => { if (settingsModal) settingsModal.style.display = "none"; });
    const btnCancelSettings = document.getElementById("btnCancelSettings");
    if (btnCancelSettings) btnCancelSettings.addEventListener("click", () => { if (settingsModal) settingsModal.style.display = "none"; });

    const btnTestConn = document.getElementById("btnTestConn");
    if (btnTestConn) btnTestConn.addEventListener("click", testTelegramConnection);
    const btnSaveSettings = document.getElementById("btnSaveSettings");
    if (btnSaveSettings) btnSaveSettings.addEventListener("click", saveSettingsToServer);

    // Empty trash
    document.getElementById("btnEmptyTrash").addEventListener("click", async () => {
        if (confirm("តើអ្នកពិតជាចង់សម្អាតធុងសំរាមមែនទេ? (Empty trash permanently?)")) {
            await fetch("/api/empty-trash", { method: "POST" });
            fetchStats();
            loadFiles();
        }
    });

    // Clear completed transfers
    document.getElementById("btnClearCompleted").addEventListener("click", () => {
        document.getElementById("transferList").innerHTML = "";
        document.getElementById("transferPanel").style.display = "none";
    });
}

function closeAllRibbonDropdowns() {
    document.querySelectorAll(".win-dropdown-menu").forEach(m => m.style.display = "none");
    document.querySelectorAll(".win-btn-dropdown").forEach(b => b.classList.remove("active"));
}

function setViewMode(mode) {
    currentView = mode;
    localStorage.setItem("win11_view_mode", mode);
    updateViewCheckmarks();
    renderFiles();
}

function updateViewCheckmarks() {
    const viewModes = ["extra-large", "large", "medium", "small", "list", "details", "tiles", "content"];
    viewModes.forEach(vm => {
        const item = document.querySelector(`.win-view-dropdown [data-view="${vm}"]`);
        if (item) {
            item.classList.toggle("active", currentView === vm);
            const chk = item.querySelector(".win-dd-check");
            if (chk) chk.textContent = currentView === vm ? "✓" : "";
        }
    });
}

function setSort(col) {
    if (currentSortCol === col) {
        currentSortDir = currentSortDir === "asc" ? "desc" : "asc";
    } else {
        currentSortCol = col;
        currentSortDir = "asc";
    }
    updateSortUI();
    renderFiles();
}

function setOrder(order) {
    currentSortDir = order;
    updateSortUI();
    renderFiles();
}

function toggleSortCol(col) {
    setSort(col);
}

function updateSortUI() {
    ["name", "date", "type", "size"].forEach(c => {
        const chk = document.getElementById(`chkSort${c.charAt(0).toUpperCase() + c.slice(1)}`);
        if (chk) chk.textContent = currentSortCol === c ? "✓" : "";
    });
    const chkAsc = document.getElementById("chkOrderAsc");
    const chkDesc = document.getElementById("chkOrderDesc");
    if (chkAsc) chkAsc.textContent = currentSortDir === "asc" ? "✓" : "";
    if (chkDesc) chkDesc.textContent = currentSortDir === "desc" ? "✓" : "";

    ["name", "date", "type", "size"].forEach(c => {
        const th = document.getElementById(`thCol${c.charAt(0).toUpperCase() + c.slice(1)}`);
        const arrow = document.getElementById(`sortArrow${c.charAt(0).toUpperCase() + c.slice(1)}`);
        if (th && arrow) {
            if (currentSortCol === c) {
                th.classList.add("active-sort");
                arrow.textContent = currentSortDir === "asc" ? "▲" : "▼";
            } else {
                th.classList.remove("active-sort");
                arrow.textContent = "";
            }
        }
    });
}

function getWin11FolderSvg(size = 22) {
    return `<svg class="win11-folder-icon" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M2.5 5.5C2.5 4.39543 3.39543 3.5 4.5 3.5H9.37868C9.90912 3.5 10.4178 3.71071 10.7929 4.08579L12.4142 5.70711C12.7893 6.08219 13.298 6.29289 13.8284 6.29289H19.5C20.6046 6.29289 21.5 7.18746 21.5 8.29289V18.5C21.5 19.6046 20.6046 20.5 19.5 20.5H4.5C3.39543 20.5 2.5 19.6046 2.5 18.5V5.5Z" fill="#D98A09"/>
        <path d="M4 8.5C4 7.67157 4.67157 7 5.5 7H18.5C19.3284 7 20 7.67157 20 8.5V11H4V8.5Z" fill="#FFF9E6" fill-opacity="0.35"/>
        <path d="M2.5 9.5C2.5 8.39543 3.39543 7.5 4.5 7.5H19.5C20.6046 7.5 21.5 8.39543 21.5 9.5V18.5C21.5 19.6046 20.6046 20.5 19.5 20.5H4.5C3.39543 20.5 2.5 19.6046 2.5 18.5V9.5Z" fill="url(#win11FolderYellowGrad_${size})"/>
        <defs>
            <linearGradient id="win11FolderYellowGrad_${size}" x1="12" y1="7.5" x2="12" y2="20.5" gradientUnits="userSpaceOnUse">
                <stop stop-color="#FFDD6B"/>
                <stop offset="0.35" stop-color="#FCCA3F"/>
                <stop offset="1" stop-color="#F5B318"/>
            </linearGradient>
        </defs>
    </svg>`;
}

function formatWinDate(dateStr) {
    if (!dateStr) return "-";
    try {
        const d = new Date(dateStr.replace(" ", "T"));
        if (isNaN(d.getTime())) return dateStr;
        const day = String(d.getDate()).padStart(2, '0');
        const month = String(d.getMonth() + 1).padStart(2, '0');
        const year = d.getFullYear();
        const hours = String(d.getHours()).padStart(2, '0');
        const minutes = String(d.getMinutes()).padStart(2, '0');
        return `${day}/${month}/${year} ${hours}:${minutes}`;
    } catch (_) {
        return dateStr;
    }
}

function formatWinSize(bytes, isFolder = false) {
    if (isFolder || bytes === undefined || bytes === null) return "";
    const kb = Math.ceil(bytes / 1024);
    return `${kb.toLocaleString()} KB`;
}

function getWinFileType(fileName, category) {
    if (!fileName) return "File";
    const ext = fileName.includes('.') ? fileName.split('.').pop().toLowerCase() : '';
    const map = {
        mp4: "MP4 Video",
        mkv: "MKV Video File",
        mov: "QuickTime Movie",
        avi: "AVI Video",
        webm: "WebM Video",
        mp3: "MP3 Audio File",
        wav: "WAV Audio File",
        flac: "FLAC Audio File",
        m4a: "M4A Audio File",
        jpg: "JPEG Image",
        jpeg: "JPEG Image",
        png: "PNG Image",
        gif: "GIF Image",
        webp: "WebP Image",
        svg: "SVG Image",
        bmp: "BMP Image",
        pdf: "Adobe Acrobat Document",
        doc: "Microsoft Word 97-2003 Document",
        docx: "Microsoft Word Document",
        xls: "Microsoft Excel Worksheet",
        xlsx: "Microsoft Excel Worksheet",
        ppt: "Microsoft PowerPoint Presentation",
        pptx: "Microsoft PowerPoint Presentation",
        txt: "Text Document",
        json: "JSON Source File",
        zip: "Compressed (zipped) Folder",
        rar: "WinRAR archive",
        "7z": "7-Zip archive",
        tar: "TAR Archive",
        gz: "GZ Archive",
        exe: "Application",
        msi: "Windows Installer Package",
        apk: "Android Package",
        dmg: "Apple Disk Image",
        iso: "Disc Image File"
    };
    if (map[ext]) return map[ext];
    if (category === "videos") return "Video File";
    if (category === "images") return "Image File";
    if (category === "music") return "Audio File";
    if (category === "documents") return "Document";
    if (category === "archives") return "Archive";
    return ext ? `${ext.toUpperCase()} File` : "File";
}

function sortItems(folders, files) {
    const sortedFolders = [...folders];
    const sortedFiles = [...files];
    const mult = currentSortDir === "asc" ? 1 : -1;

    sortedFolders.sort((a, b) => {
        if (currentSortCol === "date") {
            return mult * (new Date(a.created_at || 0) - new Date(b.created_at || 0));
        }
        return mult * (a.folder_name || "").localeCompare(b.folder_name || "");
    });

    sortedFiles.sort((a, b) => {
        if (currentSortCol === "size") {
            return mult * ((a.file_size || 0) - (b.file_size || 0));
        }
        if (currentSortCol === "date") {
            return mult * (new Date(a.created_at || 0) - new Date(b.created_at || 0));
        }
        if (currentSortCol === "type") {
            const tA = getWinFileType(a.file_name, a.category);
            const tB = getWinFileType(b.file_name, b.category);
            return mult * tA.localeCompare(tB);
        }
        return mult * (a.file_name || "").localeCompare(b.file_name || "");
    });

    return { sortedFolders, sortedFiles };
}

function openFolder(folderId, folderName) {
    currentFolderId = folderId;
    folderStack.push({ id: folderId, name: folderName });

    if (historyIndex < navHistory.length - 1) {
        navHistory = navHistory.slice(0, historyIndex + 1);
    }
    navHistory.push({ folderId: currentFolderId, stack: [...folderStack] });
    historyIndex = navHistory.length - 1;

    clearSelection();
    loadFiles();
}

function navBack() {
    if (historyIndex > 0) {
        historyIndex--;
        const item = navHistory[historyIndex];
        currentFolderId = item.folderId;
        folderStack = [...item.stack];
        clearSelection();
        loadFiles();
    }
}

function navForward() {
    if (historyIndex < navHistory.length - 1) {
        historyIndex++;
        const item = navHistory[historyIndex];
        currentFolderId = item.folderId;
        folderStack = [...item.stack];
        clearSelection();
        loadFiles();
    }
}

function navUp() {
    if (folderStack.length > 1) {
        folderStack.pop();
        const parent = folderStack[folderStack.length - 1];
        currentFolderId = parent.id;
        navHistory.push({ folderId: currentFolderId, stack: [...folderStack] });
        historyIndex = navHistory.length - 1;
        clearSelection();
        loadFiles();
    } else if (folderStack.length === 1) {
        folderStack = [];
        currentFolderId = null;
        navHistory.push({ folderId: null, stack: [] });
        historyIndex = navHistory.length - 1;
        clearSelection();
        loadFiles();
    }
}

async function fetchStats() {
    try {
        const res = await fetch("/api/stats");
        const data = await res.json();

        const usedGb = data.used_bytes / (1024 ** 3);
        const freeTb = data.free_bytes / (1024 ** 4);
        const pct = Math.min(100, Math.max(0.1, (data.used_bytes / data.total_bytes) * 100));

        let valText = "";
        if (usedGb < 1) {
            valText = `${(data.used_bytes / (1024 ** 2)).toFixed(2)} MB / 1,024,000 GB`;
        } else if (usedGb < 1024) {
            valText = `${usedGb.toFixed(2)} GB / 1,024,000 GB`;
        } else {
            valText = `${(usedGb / 1024).toFixed(2)} TB / 1,000 TB`;
        }

        const qv = document.getElementById("quotaValue");
        const qf = document.getElementById("quotaFill");
        const qs = document.getElementById("quotaSub");
        if (qv) qv.textContent = valText;
        if (qf) qf.style.width = `${pct}%`;
        if (qs) qs.textContent = `${i18n[currentLang].quota_free} ${freeTb.toFixed(2)} TB (${(100 - pct).toFixed(1)}%)`;

        const statusBtn = document.getElementById("cloudStatusBtn");
        const statusTxt = document.getElementById("cloudStatusText");
        if (statusBtn && statusTxt) {
            statusBtn.className = "status-pill connected";
            statusTxt.textContent = "Mercy Dental Care";
        }

        // HUN BUNTHA drive
        const bUsedBytes = data.buntha_bytes || 0;
        const bFreeTb = Math.max(0, (data.total_bytes - bUsedBytes) / (1024 ** 4));
        const bPct = Math.min(100, Math.max(0.1, (bUsedBytes / data.total_bytes) * 100));
        const bFill = document.getElementById("driveNavFillBuntha");
        const bSub = document.getElementById("driveNavSubBuntha");
        if (bFill) bFill.style.width = `${bPct}%`;
        if (bSub) {
            bSub.textContent = currentLang === "km" 
                ? `នៅសល់ ${bFreeTb.toFixed(2)} TB នៃ 1,000 TB`
                : `${bFreeTb.toFixed(2)} TB free of 1,000 TB`;
        }

        // NEANG VUOCHLIN drive
        const vUsedBytes = data.vuochlin_bytes || 0;
        const vFreeTb = Math.max(0, (data.total_bytes - vUsedBytes) / (1024 ** 4));
        const vPct = Math.min(100, Math.max(0.1, (vUsedBytes / data.total_bytes) * 100));
        const vFill = document.getElementById("driveNavFillVuochlin");
        const vSub = document.getElementById("driveNavSubVuochlin");
        if (vFill) vFill.style.width = `${vPct}%`;
        if (vSub) {
            vSub.textContent = currentLang === "km" 
                ? `នៅសល់ ${vFreeTb.toFixed(2)} TB នៃ 1,000 TB`
                : `${vFreeTb.toFixed(2)} TB free of 1,000 TB`;
        }

        // Mercy Dental Care drive
        const mUsedBytes = data.mercy_bytes || 0;
        const mFreeTb = Math.max(0, (data.total_bytes - mUsedBytes) / (1024 ** 4));
        const mPct = Math.min(100, Math.max(0.1, (mUsedBytes / data.total_bytes) * 100));
        const mFill = document.getElementById("driveNavFillMercy");
        const mSub = document.getElementById("driveNavSubMercy");
        if (mFill) mFill.style.width = `${mPct}%`;
        if (mSub) {
            mSub.textContent = currentLang === "km" 
                ? `នៅសល់ ${mFreeTb.toFixed(2)} TB នៃ 1,000 TB`
                : `${mFreeTb.toFixed(2)} TB free of 1,000 TB`;
        }
    } catch (e) {
        console.error("Error fetching stats:", e);
    }
}

async function loadFiles() {
    try {
        let url = `/api/files?category=${currentCategory}&search=${encodeURIComponent(currentSearch)}`;
        if (currentFolderId) {
            url += `&folder_id=${currentFolderId}`;
        }
        const res = await fetch(url);
        const data = await res.json();
        filesData = data.files || [];
        foldersData = data.folders || [];
        renderBreadcrumbs();
        renderFolders();
        renderFiles();
    } catch (e) {
        console.error("Error loading files:", e);
    }
}

function renderBreadcrumbs() {
    const trail = document.getElementById("breadcrumbsTrail");
    let rootName = "HUN BUNTHA";
    if (currentCategory === "vuochlin") rootName = "NEANG VUOCHLIN";
    else if (currentCategory === "mercy") rootName = "Mercy Dental Care";
    else if (currentCategory === "trash") rootName = "ធុងសំរាម (Trash)";

    // Update Tab Title
    let activeTabTitle = document.getElementById("tabTitleBuntha");
    if (currentCategory === "vuochlin") activeTabTitle = document.getElementById("tabTitleVuochlin");
    else if (currentCategory === "mercy") activeTabTitle = document.getElementById("tabTitleMercy");
    if (activeTabTitle) {
        if (folderStack.length > 0) {
            activeTabTitle.textContent = folderStack[folderStack.length - 1].name;
        } else {
            activeTabTitle.textContent = rootName;
        }
    }

    // Update Navigation Buttons
    const btnNavBack = document.getElementById("btnNavBack");
    const btnNavForward = document.getElementById("btnNavForward");
    const btnNavUp = document.getElementById("btnNavUp");
    if (btnNavBack) btnNavBack.disabled = historyIndex <= 0;
    if (btnNavForward) btnNavForward.disabled = historyIndex >= navHistory.length - 1;
    if (btnNavUp) btnNavUp.disabled = folderStack.length === 0;

    if (!trail) return;

    trail.innerHTML = `
        <button class="breadcrumb-item root ${folderStack.length === 0 ? 'active' : ''}" id="crumbRoot" title="Root Drive">
            <span class="crumb-icon">${currentCategory === 'trash' ? '🗑️' : '💾'}</span>
            <span>${rootName}</span>
        </button>
    `;

    const crumbRoot = document.getElementById("crumbRoot");
    if (crumbRoot) {
        crumbRoot.addEventListener("click", () => {
            currentFolderId = null;
            folderStack = [];
            if (historyIndex < navHistory.length - 1) {
                navHistory = navHistory.slice(0, historyIndex + 1);
            }
            navHistory.push({ folderId: null, stack: [] });
            historyIndex = navHistory.length - 1;
            clearSelection();
            loadFiles();
        });

        crumbRoot.addEventListener("dragover", (e) => {
            e.preventDefault();
            e.dataTransfer.dropEffect = "move";
            crumbRoot.classList.add("drag-target-hover");
        });
        crumbRoot.addEventListener("dragleave", () => crumbRoot.classList.remove("drag-target-hover"));
        crumbRoot.addEventListener("drop", (e) => {
            e.preventDefault();
            crumbRoot.classList.remove("drag-target-hover");
            const { fileIds, folderIds } = getDraggedItems(e);
            if (folderIds && folderIds.length > 0) {
                moveFoldersToFolder(folderIds, null, rootName);
            }
            if (fileIds && fileIds.length > 0) {
                moveFilesToFolder(fileIds, null, rootName);
            }
        });
    }

    folderStack.forEach((crumb, idx) => {
        const sep = document.createElement("span");
        sep.className = "win-crumb-sep";
        sep.textContent = "›";
        trail.appendChild(sep);

        const btn = document.createElement("button");
        btn.className = `breadcrumb-item ${idx === folderStack.length - 1 ? 'active' : ''}`;
        btn.innerHTML = `<span>📁</span> <span>${crumb.name}</span>`;
        btn.addEventListener("click", () => {
            currentFolderId = crumb.id;
            folderStack = folderStack.slice(0, idx + 1);
            if (historyIndex < navHistory.length - 1) {
                navHistory = navHistory.slice(0, historyIndex + 1);
            }
            navHistory.push({ folderId: currentFolderId, stack: [...folderStack] });
            historyIndex = navHistory.length - 1;
            clearSelection();
            loadFiles();
        });

        btn.addEventListener("dragover", (e) => {
            e.preventDefault();
            e.dataTransfer.dropEffect = "move";
            btn.classList.add("drag-target-hover");
        });
        btn.addEventListener("dragleave", () => btn.classList.remove("drag-target-hover"));
        btn.addEventListener("drop", (e) => {
            e.preventDefault();
            btn.classList.remove("drag-target-hover");
            const { fileIds, folderIds } = getDraggedItems(e);
            const validFolders = (folderIds || []).filter(id => id !== crumb.id);
            if (validFolders.length > 0) {
                moveFoldersToFolder(validFolders, crumb.id, crumb.name);
            }
            if (fileIds && fileIds.length > 0) {
                moveFilesToFolder(fileIds, crumb.id, crumb.name);
            }
        });

        trail.appendChild(btn);
    });
}

function renderFolders() {
    // Kept for backward compatibility; rendering is unified in renderFiles()
}

function getDraggedItems(e) {
    let fileIds = [];
    let folderIds = [];
    try {
        const raw = e.dataTransfer.getData("application/json");
        if (raw) {
            const parsed = JSON.parse(raw);
            if (Array.isArray(parsed)) {
                fileIds = parsed;
            } else if (parsed && typeof parsed === "object") {
                fileIds = parsed.file_ids || [];
                folderIds = parsed.folder_ids || [];
            }
        }
    } catch (_) {}
    try {
        const rawF = e.dataTransfer.getData("application/folder-ids");
        if (rawF) {
            const fArr = JSON.parse(rawF);
            if (Array.isArray(fArr)) {
                folderIds = Array.from(new Set([...folderIds, ...fArr]));
            }
        }
    } catch (_) {}
    try {
        const rawFiles = e.dataTransfer.getData("application/file-ids");
        if (rawFiles) {
            const flArr = JSON.parse(rawFiles);
            if (Array.isArray(flArr)) {
                fileIds = Array.from(new Set([...fileIds, ...flArr]));
            }
        }
    } catch (_) {}

    if (fileIds.length === 0 && folderIds.length === 0) {
        if (selectedFileIds.size > 0) fileIds = Array.from(selectedFileIds);
        if (selectedFolderIds.size > 0) folderIds = Array.from(selectedFolderIds);
    }
    return { fileIds, folderIds };
}

function getDraggedFileIds(e) {
    return getDraggedItems(e).fileIds;
}

function getFileIcon(cat) {
    const map = {
        documents: "📄",
        images: "🖼️",
        videos: "🎬",
        music: "🎵",
        archives: "📦",
        others: "📁"
    };
    return map[cat] || "📁";
}

function formatSize(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 ** 2) return (bytes / 1024).toFixed(2) + " KB";
    if (bytes < 1024 ** 3) return (bytes / (1024 ** 2)).toFixed(2) + " MB";
    return (bytes / (1024 ** 3)).toFixed(2) + " GB";
}

/* Unified Windows 11 Explorer Renderer: Folders + Files Combined */
function renderFiles() {
    const detailsContainer = document.getElementById("winDetailsContainer");
    const itemsView = document.getElementById("winItemsView");
    const tbody = document.getElementById("winDetailsTbody");
    const emptyState = document.getElementById("emptyState");

    updateViewCheckmarks();
    updateSortUI();

    const hasFolders = foldersData && foldersData.length > 0;
    const hasFiles = filesData && filesData.length > 0;

    if (!hasFiles && !hasFolders) {
        if (detailsContainer) detailsContainer.style.display = "none";
        if (itemsView) itemsView.style.display = "none";
        if (emptyState) emptyState.style.display = "block";
        updateSelectionUI();
        return;
    }

    if (emptyState) emptyState.style.display = "none";

    const { sortedFolders, sortedFiles } = sortItems(foldersData, filesData);

    if (currentView === "details") {
        if (detailsContainer) detailsContainer.style.display = "block";
        if (itemsView) itemsView.style.display = "none";
        if (!tbody) return;
        tbody.innerHTML = "";

        // 1. Render Folders in Details View (Picture 2)
        sortedFolders.forEach(folder => {
            const tr = document.createElement("tr");
            const isSel = selectedFolderIds.has(folder.id);
            tr.className = `win-row folder-row ${isSel ? 'selected' : ''}`;
            tr.dataset.folderId = folder.id;
            tr.dataset.folderName = folder.folder_name;

            tr.innerHTML = `
                <td class="col-check">
                    <input type="checkbox" class="win-checkbox row-select-cb folder-select-cb" ${isSel ? 'checked' : ''}>
                </td>
                <td class="col-name">
                    <div class="item-name-cell">
                        ${getWin11FolderSvg(22)}
                        <span class="item-name-text" title="${folder.folder_name}">${folder.folder_name}</span>
                    </div>
                </td>
                <td class="col-date">${formatWinDate(folder.created_at)}</td>
                <td class="col-type">File folder</td>
                <td class="col-size"></td>
                <td class="col-actions">
                    <div class="row-actions">
                        <button class="btn-row-act btn-f-rename" title="Rename (ប្តូរឈ្មោះ)">✏️</button>
                        <button class="btn-row-act btn-f-del" title="Delete (លុបថត)">🗑️</button>
                    </div>
                </td>
            `;

            // Open folder on name click or double click
            tr.querySelector(".item-name-cell").addEventListener("click", (e) => {
                e.stopPropagation();
                openFolder(folder.id, folder.folder_name);
            });
            tr.addEventListener("dblclick", () => {
                openFolder(folder.id, folder.folder_name);
            });

            // Single click row selection
            tr.addEventListener("click", (e) => {
                if (e.target.closest(".row-actions") || e.target.closest(".win-checkbox")) return;
                if (e.ctrlKey || e.metaKey || selectedFolderIds.size > 0 || selectedFileIds.size > 0) {
                    toggleSelectFolder(folder.id);
                } else {
                    clearSelection();
                    toggleSelectFolder(folder.id);
                }
            });

            // Checkbox click
            const cb = tr.querySelector(".folder-select-cb");
            if (cb) {
                cb.addEventListener("click", (e) => {
                    e.stopPropagation();
                    toggleSelectFolder(folder.id);
                });
            }

            // Folder row actions
            const btnRename = tr.querySelector(".btn-f-rename");
            if (btnRename) {
                btnRename.addEventListener("click", (e) => {
                    e.stopPropagation();
                    promptRenameFolder(folder.id, folder.folder_name);
                });
            }
            const btnDel = tr.querySelector(".btn-f-del");
            if (btnDel) {
                btnDel.addEventListener("click", (e) => {
                    e.stopPropagation();
                    confirmDeleteFolder(folder.id, folder.folder_name);
                });
            }

            // Context menu
            tr.addEventListener("contextmenu", (e) => {
                e.preventDefault();
                e.stopPropagation();
                showFolderContextMenu(e.clientX, e.clientY, folder);
            });

            // Make folder row draggable
            tr.draggable = true;
            tr.addEventListener("dragstart", (e) => {
                if (!selectedFolderIds.has(folder.id)) {
                    if (selectedFolderIds.size === 0 && selectedFileIds.size === 0) {
                        selectedFolderIds.add(folder.id);
                        updateSelectionUI();
                    }
                }
                const dragFolderIds = selectedFolderIds.has(folder.id) ? Array.from(selectedFolderIds) : [folder.id];
                const dragFileIds = Array.from(selectedFileIds);
                const payload = {
                    type: "items",
                    folder_ids: dragFolderIds,
                    file_ids: dragFileIds
                };
                e.dataTransfer.setData("application/json", JSON.stringify(payload));
                e.dataTransfer.setData("application/folder-ids", JSON.stringify(dragFolderIds));
                if (dragFileIds.length > 0) {
                    e.dataTransfer.setData("application/file-ids", JSON.stringify(dragFileIds));
                }
                e.dataTransfer.effectAllowed = "move";
                isInternalDragging = true;
                tr.classList.add("dragging");
            });

            tr.addEventListener("dragend", () => {
                isInternalDragging = false;
                tr.classList.remove("dragging");
                document.querySelectorAll(".drag-target-hover").forEach(el => el.classList.remove("drag-target-hover"));
            });

            // Drag & Drop Target: Move folders or files into this folder
            tr.addEventListener("dragover", (e) => {
                e.preventDefault();
                e.stopPropagation();
                e.dataTransfer.dropEffect = "move";
                tr.classList.add("drag-target-hover");
            });
            tr.addEventListener("dragleave", (e) => {
                if (!tr.contains(e.relatedTarget)) {
                    tr.classList.remove("drag-target-hover");
                }
            });
            tr.addEventListener("drop", (e) => {
                e.preventDefault();
                e.stopPropagation();
                tr.classList.remove("drag-target-hover");
                const { fileIds, folderIds } = getDraggedItems(e);
                const validFolders = (folderIds || []).filter(id => id !== folder.id);
                if (validFolders.length > 0) {
                    moveFoldersToFolder(validFolders, folder.id, folder.folder_name);
                }
                if (fileIds && fileIds.length > 0) {
                    moveFilesToFolder(fileIds, folder.id, folder.folder_name);
                }
            });

            tbody.appendChild(tr);
        });

        // 2. Render Files in Details View (Picture 2)
        sortedFiles.forEach(file => {
            const tr = document.createElement("tr");
            const isSel = selectedFileIds.has(file.id);
            tr.className = `win-row file-row ${isSel ? 'selected' : ''}`;
            tr.dataset.fileId = file.id;
            tr.dataset.fileName = file.file_name;
            tr.draggable = true;

            const icon = getFileIcon(file.category);
            const winType = getWinFileType(file.file_name, file.category);
            const winSize = formatWinSize(file.file_size);

            tr.innerHTML = `
                <td class="col-check">
                    <input type="checkbox" class="win-checkbox row-select-cb file-select-cb" ${isSel ? 'checked' : ''}>
                </td>
                <td class="col-name">
                    <div class="item-name-cell">
                        <div class="item-icon-wrap">${icon}</div>
                        <span class="item-name-text" title="${file.file_name}">${file.file_name}</span>
                    </div>
                </td>
                <td class="col-date">${formatWinDate(file.created_at)}</td>
                <td class="col-type">${winType}</td>
                <td class="col-size">${winSize}</td>
                <td class="col-actions">
                    <div class="row-actions">
                        ${!file.is_trash ? `
                            <button class="btn-row-act btn-view" title="${currentLang === 'km' ? 'បើកមើល' : 'View'}">👁️</button>
                            <button class="btn-row-act btn-dl" title="${i18n[currentLang].download}">📥</button>
                            <button class="btn-row-act btn-del" title="${i18n[currentLang].delete}">🗑️</button>
                        ` : `
                            <button class="btn-row-act btn-restore" title="${i18n[currentLang].restore}">♻️</button>
                            <button class="btn-row-act btn-perm" style="color: #f43f5e;" title="${i18n[currentLang].permanent}">❌</button>
                        `}
                    </div>
                </td>
            `;

            // Double click opens preview or downloads
            tr.addEventListener("dblclick", () => {
                if (!file.is_trash) previewFile(file.id);
            });

            // Single click row selection
            tr.addEventListener("click", (e) => {
                if (e.target.closest(".row-actions") || e.target.closest(".win-checkbox")) return;
                if (e.ctrlKey || e.metaKey || selectedFileIds.size > 0 || selectedFolderIds.size > 0) {
                    toggleSelectFile(file.id);
                } else {
                    clearSelection();
                    toggleSelectFile(file.id);
                }
            });

            // Checkbox click
            const cb = tr.querySelector(".file-select-cb");
            if (cb) {
                cb.addEventListener("click", (e) => {
                    e.stopPropagation();
                    toggleSelectFile(file.id);
                });
            }

            // Dragstart for moving
            tr.addEventListener("dragstart", (e) => {
                if (!selectedFileIds.has(file.id)) {
                    if (selectedFileIds.size === 0 && selectedFolderIds.size === 0) {
                        selectedFileIds.add(file.id);
                        updateSelectionUI();
                    }
                }
                const dragFileIds = selectedFileIds.has(file.id) ? Array.from(selectedFileIds) : [file.id];
                const dragFolderIds = Array.from(selectedFolderIds);
                const payload = {
                    type: "items",
                    folder_ids: dragFolderIds,
                    file_ids: dragFileIds
                };
                e.dataTransfer.setData("application/json", JSON.stringify(payload));
                e.dataTransfer.setData("application/file-ids", JSON.stringify(dragFileIds));
                if (dragFolderIds.length > 0) {
                    e.dataTransfer.setData("application/folder-ids", JSON.stringify(dragFolderIds));
                }
                e.dataTransfer.effectAllowed = "move";
                isInternalDragging = true;
                tr.classList.add("dragging");
            });

            tr.addEventListener("dragend", () => {
                isInternalDragging = false;
                tr.classList.remove("dragging");
                document.querySelectorAll(".drag-target-hover").forEach(el => el.classList.remove("drag-target-hover"));
            });

            // File row quick actions
            if (!file.is_trash) {
                const btnV = tr.querySelector(".btn-view");
                if (btnV) btnV.addEventListener("click", (e) => { e.stopPropagation(); previewFile(file.id); });
                const btnD = tr.querySelector(".btn-dl");
                if (btnD) btnD.addEventListener("click", (e) => { e.stopPropagation(); downloadFile(file.id); });
                const btnDel = tr.querySelector(".btn-del");
                if (btnDel) btnDel.addEventListener("click", (e) => { e.stopPropagation(); trashFile(file.id); });
            } else {
                const btnRes = tr.querySelector(".btn-restore");
                if (btnRes) btnRes.addEventListener("click", (e) => { e.stopPropagation(); restoreFile(file.id); });
                const btnPerm = tr.querySelector(".btn-perm");
                if (btnPerm) btnPerm.addEventListener("click", (e) => { e.stopPropagation(); deletePermanent(file.id); });
            }

            // Context menu
            tr.addEventListener("contextmenu", (e) => {
                e.preventDefault();
                e.stopPropagation();
                showFileContextMenu(e.clientX, e.clientY, file);
            });

            tbody.appendChild(tr);
        });

    } else {
        // Icon View Modes: Extra-large, Large, Medium, Small, List, Tiles, Content
        if (detailsContainer) detailsContainer.style.display = "none";
        if (itemsView) {
            itemsView.style.display = "grid";
            itemsView.className = `win-items-view view-${currentView}`;
            itemsView.innerHTML = "";

            const iconSizeMap = {
                "extra-large": 110,
                "large": 76,
                "medium": 50,
                "small": 24,
                "list": 20,
                "tiles": 42,
                "content": 36
            };
            const iconSize = iconSizeMap[currentView] || 50;

            // Render Folders in Icon View
            sortedFolders.forEach(folder => {
                const card = document.createElement("div");
                const isSel = selectedFolderIds.has(folder.id);
                card.className = `win-item-card folder-card ${isSel ? 'selected' : ''}`;
                card.dataset.folderId = folder.id;
                card.dataset.folderName = folder.folder_name;

                card.innerHTML = `
                    <div class="item-icon-box">
                        ${getWin11FolderSvg(iconSize)}
                    </div>
                    <div class="item-label-box">
                        <div class="item-main-title" title="${folder.folder_name}">${folder.folder_name}</div>
                        ${(currentView === "tiles" || currentView === "content") ? `<div class="item-sub-info">File folder</div>` : ''}
                    </div>
                `;

                card.addEventListener("click", (e) => {
                    if (e.ctrlKey || e.metaKey || selectedFolderIds.size > 0 || selectedFileIds.size > 0) {
                        toggleSelectFolder(folder.id);
                    } else {
                        openFolder(folder.id, folder.folder_name);
                    }
                });

                card.addEventListener("dblclick", () => {
                    openFolder(folder.id, folder.folder_name);
                });

                card.addEventListener("contextmenu", (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    showFolderContextMenu(e.clientX, e.clientY, folder);
                });

                // Make folder card draggable
                card.draggable = true;
                card.addEventListener("dragstart", (e) => {
                    if (!selectedFolderIds.has(folder.id)) {
                        if (selectedFolderIds.size === 0 && selectedFileIds.size === 0) {
                            selectedFolderIds.add(folder.id);
                            updateSelectionUI();
                        }
                    }
                    const dragFolderIds = selectedFolderIds.has(folder.id) ? Array.from(selectedFolderIds) : [folder.id];
                    const dragFileIds = Array.from(selectedFileIds);
                    const payload = {
                        type: "items",
                        folder_ids: dragFolderIds,
                        file_ids: dragFileIds
                    };
                    e.dataTransfer.setData("application/json", JSON.stringify(payload));
                    e.dataTransfer.setData("application/folder-ids", JSON.stringify(dragFolderIds));
                    if (dragFileIds.length > 0) {
                        e.dataTransfer.setData("application/file-ids", JSON.stringify(dragFileIds));
                    }
                    e.dataTransfer.effectAllowed = "move";
                    isInternalDragging = true;
                    card.classList.add("dragging");
                });

                card.addEventListener("dragend", () => {
                    isInternalDragging = false;
                    card.classList.remove("dragging");
                    document.querySelectorAll(".drag-target-hover").forEach(el => el.classList.remove("drag-target-hover"));
                });

                // Drop target: move folders or files into folder
                card.addEventListener("dragover", (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    e.dataTransfer.dropEffect = "move";
                    card.classList.add("drag-target-hover");
                });
                card.addEventListener("dragleave", (e) => {
                    if (!card.contains(e.relatedTarget)) {
                        card.classList.remove("drag-target-hover");
                    }
                });
                card.addEventListener("drop", (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    card.classList.remove("drag-target-hover");
                    const { fileIds, folderIds } = getDraggedItems(e);
                    const validFolders = (folderIds || []).filter(id => id !== folder.id);
                    if (validFolders.length > 0) {
                        moveFoldersToFolder(validFolders, folder.id, folder.folder_name);
                    }
                    if (fileIds && fileIds.length > 0) {
                        moveFilesToFolder(fileIds, folder.id, folder.folder_name);
                    }
                });

                itemsView.appendChild(card);
            });

            // Render Files in Icon View
            sortedFiles.forEach(file => {
                const card = document.createElement("div");
                const isSel = selectedFileIds.has(file.id);
                card.className = `win-item-card file-card ${isSel ? 'selected' : ''}`;
                card.dataset.fileId = file.id;
                card.dataset.fileName = file.file_name;
                card.draggable = true;

                const icon = getFileIcon(file.category);
                const winType = getWinFileType(file.file_name, file.category);
                const winSize = formatWinSize(file.file_size);
                const ext = file.file_name.toLowerCase().split('.').pop();
                const isImage = file.category === "images" || ['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg'].includes(ext);

                card.innerHTML = `
                    <div class="item-icon-box">
                        ${isImage && (currentView === "extra-large" || currentView === "large" || currentView === "medium")
                            ? `<img src="/api/view/${file.id}" alt="${file.file_name}" class="item-thumb-img" loading="lazy" onerror="this.outerHTML='<span style=\\'font-size:${iconSize}px\\'>${icon}</span>'">`
                            : `<span style="font-size: ${iconSize}px;">${icon}</span>`}
                    </div>
                    <div class="item-label-box">
                        <div class="item-main-title" title="${file.file_name}">${file.file_name}</div>
                        ${(currentView === "tiles" || currentView === "content") ? `<div class="item-sub-info">${winType} • ${winSize}</div>` : ''}
                    </div>
                `;

                card.addEventListener("click", (e) => {
                    if (e.ctrlKey || e.metaKey || selectedFileIds.size > 0 || selectedFolderIds.size > 0) {
                        toggleSelectFile(file.id);
                    } else {
                        if (!file.is_trash) previewFile(file.id);
                    }
                });

                card.addEventListener("dragstart", (e) => {
                    if (!selectedFileIds.has(file.id)) {
                        if (selectedFileIds.size === 0 && selectedFolderIds.size === 0) {
                            selectedFileIds.add(file.id);
                            updateSelectionUI();
                        }
                    }
                    const dragFileIds = selectedFileIds.has(file.id) ? Array.from(selectedFileIds) : [file.id];
                    const dragFolderIds = Array.from(selectedFolderIds);
                    const payload = {
                        type: "items",
                        folder_ids: dragFolderIds,
                        file_ids: dragFileIds
                    };
                    e.dataTransfer.setData("application/json", JSON.stringify(payload));
                    e.dataTransfer.setData("application/file-ids", JSON.stringify(dragFileIds));
                    if (dragFolderIds.length > 0) {
                        e.dataTransfer.setData("application/folder-ids", JSON.stringify(dragFolderIds));
                    }
                    e.dataTransfer.effectAllowed = "move";
                    isInternalDragging = true;
                    card.classList.add("dragging");
                });

                card.addEventListener("dragend", () => {
                    isInternalDragging = false;
                    card.classList.remove("dragging");
                    document.querySelectorAll(".drag-target-hover").forEach(el => el.classList.remove("drag-target-hover"));
                });

                card.addEventListener("contextmenu", (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    showFileContextMenu(e.clientX, e.clientY, file);
                });

                itemsView.appendChild(card);
            });
        }
    }

    updateSelectionUI();
}

/* ==========================================================================
   Multi-Selection Logic (Files & Folders)
   ========================================================================== */
function toggleSelectFile(id) {
    if (selectedFileIds.has(id)) {
        selectedFileIds.delete(id);
    } else {
        selectedFileIds.add(id);
    }
    updateSelectionUI();
}

function toggleSelectFolder(id) {
    if (selectedFolderIds.has(id)) {
        selectedFolderIds.delete(id);
    } else {
        selectedFolderIds.add(id);
    }
    updateSelectionUI();
}

function selectAllFiles() {
    const totalItems = filesData.length + foldersData.length;
    const currentSelected = selectedFileIds.size + selectedFolderIds.size;

    if (currentSelected === totalItems && totalItems > 0) {
        clearSelection();
    } else {
        selectedFileIds.clear();
        selectedFolderIds.clear();
        filesData.forEach(f => selectedFileIds.add(f.id));
        foldersData.forEach(f => selectedFolderIds.add(f.id));
    }
    updateSelectionUI();
}

function clearSelection() {
    selectedFileIds.clear();
    selectedFolderIds.clear();
    updateSelectionUI();
}

function updateSelectionUI() {
    const totalCount = selectedFileIds.size + selectedFolderIds.size;
    const bar = document.getElementById("selectionFloatingBar");
    const countText = document.getElementById("selectionCountText");
    const txtSelectAll = document.getElementById("txtSelectAll");
    const btnSelectAll = document.getElementById("btnToggleSelectAll");
    const thMasterCheckbox = document.getElementById("thMasterCheckbox");

    // Master Table Checkbox State
    if (thMasterCheckbox) {
        const total = filesData.length + foldersData.length;
        thMasterCheckbox.checked = total > 0 && totalCount === total;
        thMasterCheckbox.indeterminate = totalCount > 0 && totalCount < total;
    }

    // Ribbon Action Buttons Enabled/Disabled
    const btnRibbonCut = document.getElementById("btnRibbonCut");
    const btnRibbonCopy = document.getElementById("btnRibbonCopy");
    const btnRibbonRename = document.getElementById("btnRibbonRename");
    const btnRibbonDelete = document.getElementById("btnRibbonDelete");

    if (btnRibbonCut) btnRibbonCut.disabled = totalCount === 0;
    if (btnRibbonCopy) btnRibbonCopy.disabled = selectedFileIds.size === 0;
    if (btnRibbonRename) btnRibbonRename.disabled = totalCount !== 1;
    if (btnRibbonDelete) btnRibbonDelete.disabled = totalCount === 0;

    if (totalCount > 0) {
        document.body.classList.add("has-selection");
        if (bar) bar.style.display = "flex";
        if (countText) {
            countText.textContent = currentLang === "km"
                ? `${totalCount} ធាតុបានជ្រើសរើស (Items selected)`
                : `${totalCount} item${totalCount > 1 ? 's' : ''} selected`;
        }
    } else {
        document.body.classList.remove("has-selection");
        if (bar) bar.style.display = "none";
    }

    if (txtSelectAll) {
        const total = filesData.length + foldersData.length;
        txtSelectAll.textContent = (totalCount === total && total > 0)
            ? (currentLang === "km" ? "ដោះជម្រើសទាំងអស់" : "Deselect All")
            : (currentLang === "km" ? "ជ្រើសទាំងអស់" : "Select All");
    }
    if (btnSelectAll) {
        btnSelectAll.classList.toggle("active", totalCount > 0);
    }

    // Update details table row classes & checkboxes
    document.querySelectorAll(".win-details-table tbody tr.file-row").forEach(tr => {
        const id = parseInt(tr.dataset.fileId);
        const isSel = selectedFileIds.has(id);
        tr.classList.toggle("selected", isSel);
        const cb = tr.querySelector(".file-select-cb");
        if (cb) cb.checked = isSel;
    });

    document.querySelectorAll(".win-details-table tbody tr.folder-row").forEach(tr => {
        const id = parseInt(tr.dataset.folderId);
        const isSel = selectedFolderIds.has(id);
        tr.classList.toggle("selected", isSel);
        const cb = tr.querySelector(".folder-select-cb");
        if (cb) cb.checked = isSel;
    });

    // Update icon view cards
    document.querySelectorAll(".win-items-view .file-card").forEach(card => {
        const id = parseInt(card.dataset.fileId);
        card.classList.toggle("selected", selectedFileIds.has(id));
    });

    document.querySelectorAll(".win-items-view .folder-card").forEach(card => {
        const id = parseInt(card.dataset.folderId);
        card.classList.toggle("selected", selectedFolderIds.has(id));
    });
}

/* ==========================================================================
   Move Files & Folders Logic ("ទាញចូល folder")
   ========================================================================== */
async function moveFilesToFolder(fileIds, targetFolderId, targetFolderName) {
    if (!fileIds || fileIds.length === 0) return;
    try {
        const res = await fetch("/api/files/move", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                file_ids: fileIds,
                target_folder_id: targetFolderId
            })
        });
        const data = await res.json();
        if (data.success) {
            showMoveNotification(fileIds.length, targetFolderName || "Folder", false);
            clearSelection();
            loadFiles();
        } else {
            alert(data.error || "Failed to move files");
        }
    } catch (e) {
        console.error("Error moving files:", e);
        alert("Error moving files: " + e.message);
    }
}

async function moveFoldersToFolder(folderIds, targetFolderId, targetFolderName) {
    const cleanIds = (folderIds || []).filter(id => id !== targetFolderId);
    if (!cleanIds || cleanIds.length === 0) return;
    try {
        const res = await fetch("/api/folders/move", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                folder_ids: cleanIds,
                target_folder_id: targetFolderId
            })
        });
        const data = await res.json();
        if (data.success) {
            showMoveNotification(cleanIds.length, targetFolderName || "Folder", true);
            clearSelection();
            loadFiles();
        } else {
            alert(data.error || "Failed to move folders");
        }
    } catch (e) {
        console.error("Error moving folders:", e);
        alert("Error moving folders: " + e.message);
    }
}

function showMoveNotification(count, folderName, isFolder = false) {
    const toast = document.createElement("div");
    toast.className = "move-toast";
    toast.style.cssText = `
        position: fixed;
        top: 24px;
        left: 50%;
        transform: translateX(-50%);
        background: rgba(16, 185, 129, 0.95);
        color: #ffffff;
        padding: 10px 22px;
        border-radius: 30px;
        font-size: 14px;
        font-weight: 600;
        box-shadow: 0 10px 30px rgba(0,0,0,0.4);
        z-index: 100000;
        animation: winContextMenuIn 0.2s cubic-bezier(0, 0, 0.2, 1);
        display: flex;
        align-items: center;
        gap: 8px;
    `;
    const itemType = isFolder 
        ? (currentLang === "km" ? "ថត (Folder)" : "folder(s)") 
        : (currentLang === "km" ? "ឯកសារ" : "file(s)");
    toast.innerHTML = `<span>✓</span> <span>បានផ្លាស់ទី ${count} ${itemType} ចូលទៅក្នុងថត [${folderName}] ដោយជោគជ័យ!</span>`;
    document.body.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = "0";
        toast.style.transition = "opacity 0.3s ease";
        setTimeout(() => toast.remove(), 300);
    }, 2800);
}

async function openMoveModal(fileIds = [], folderIds = []) {
    const modal = document.getElementById("moveModal");
    const list = document.getElementById("moveFolderList");
    if (!modal || !list) return;

    list.innerHTML = `<div style="color: #94a3b8; padding: 10px; font-size: 13px;">កំពុងទាញយកបញ្ជី Folder...</div>`;
    modal.style.display = "flex";

    const driveOwner = (currentCategory === "vuochlin" || currentCategory === "mercy") ? currentCategory : "buntha";
    const driveLabel = driveOwner === "vuochlin" ? "NEANG VUOCHLIN" : (driveOwner === "mercy" ? "Mercy Dental Care" : "HUN BUNTHA");

    try {
        const res = await fetch(`/api/files?category=${driveOwner}`);
        const data = await res.json();
        const allFolders = data.folders || [];

        list.innerHTML = "";

        const fIdSet = new Set(folderIds || []);

        // Option 1: Move to Root Drive (if inside a folder)
        if (currentFolderId !== null) {
            const rootItem = document.createElement("div");
            rootItem.className = "folder-dest-item";
            rootItem.innerHTML = `
                <span style="font-size: 22px;">💾</span>
                <div>
                    <div class="folder-dest-name">${driveLabel} (Root)</div>
                    <div style="font-size: 11px; color: var(--text-muted);">ផ្លាស់ទីមកខាងក្រៅ Drive ដើម</div>
                </div>
            `;
            rootItem.addEventListener("click", () => {
                modal.style.display = "none";
                if (fileIds && fileIds.length > 0) moveFilesToFolder(fileIds, null, "Root Drive");
                if (folderIds && folderIds.length > 0) moveFoldersToFolder(folderIds, null, "Root Drive");
            });
            list.appendChild(rootItem);
        }

        const availableFolders = allFolders.filter(f => f.id !== currentFolderId && !fIdSet.has(f.id));

        if (availableFolders.length === 0 && currentFolderId === null) {
            list.innerHTML = `<div style="color: #94a3b8; padding: 14px; text-align: center; font-size: 13px;">មិនទាន់មាន Folder ផ្សេងសម្រាប់ផ្លាស់ទីចូលទេ។ សូមបង្កើត Folder ថ្មីជាមុនសិន។</div>`;
            return;
        }

        availableFolders.forEach(f => {
            const item = document.createElement("div");
            item.className = "folder-dest-item";
            item.innerHTML = `
                <span style="font-size: 22px;">📁</span>
                <div>
                    <div class="folder-dest-name">${f.folder_name}</div>
                    <div style="font-size: 11px; color: var(--text-muted);">${f.created_at || 'Folder'}</div>
                </div>
            `;
            item.addEventListener("click", () => {
                modal.style.display = "none";
                if (fileIds && fileIds.length > 0) moveFilesToFolder(fileIds, f.id, f.folder_name);
                if (folderIds && folderIds.length > 0) moveFoldersToFolder(folderIds, f.id, f.folder_name);
            });
            list.appendChild(item);
        });

    } catch (err) {
        list.innerHTML = `<div style="color: #f43f5e; padding: 10px;">Error: ${err.message}</div>`;
    }
}

async function deleteSelectedFiles() {
    const fileCount = selectedFileIds.size;
    const folderCount = selectedFolderIds.size;
    const total = fileCount + folderCount;
    if (total === 0) return;
    const msg = currentLang === "km"
        ? `តើអ្នកពិតជាចង់លុប ${total} ធាតុដែលបានជ្រើសរើស (${folderCount > 0 ? folderCount + ' ថត, ' : ''}${fileCount} ឯកសារ) មែនទេ?`
        : `Are you sure you want to delete ${total} selected item(s)?`;
    if (!confirm(msg)) return;

    try {
        if (fileCount > 0) {
            await fetch("/api/files/batch-trash", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ file_ids: Array.from(selectedFileIds) })
            });
        }
        if (folderCount > 0) {
            for (const fId of selectedFolderIds) {
                await fetch("/api/folders/delete", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ folder_id: fId })
                });
            }
        }
        clearSelection();
        fetchStats();
        loadFiles();
    } catch (e) {
        console.error(e);
}

// Upload Handling
async function handleFilesUpload(files, targetDrive) {
    const driveToUse = targetDrive || (currentCategory === "vuochlin" ? "vuochlin" : "buntha");
    const driveLabel = driveToUse === "vuochlin" ? "NEANG VUOCHLIN" : "HUN BUNTHA";

    const panel = document.getElementById("transferPanel");
    const list = document.getElementById("transferList");
    panel.style.display = "block";

    for (const file of files) {
        const item = document.createElement("div");
        item.className = "transfer-item";
        item.innerHTML = `
            <div class="transfer-info">
                <span>📤 ${file.name}</span>
                <span class="status-txt">កំពុងផ្ទុកចូល Drive [${driveLabel}]...</span>
            </div>
            <div class="progress-bar-bg">
                <div class="progress-bar-fill" style="width: 25%;"></div>
            </div>
        `;
        list.appendChild(item);

        const formData = new FormData();
        formData.append("file", file);
        formData.append("drive", driveToUse);
        if (currentFolderId) {
            formData.append("folder_id", currentFolderId);
        }

        try {
            const fill = item.querySelector(".progress-bar-fill");
            const status = item.querySelector(".status-txt");
            fill.style.width = "65%";

            const res = await fetch("/api/upload", {
                method: "POST",
                body: formData
            });

            const result = await res.json();
            if (result.success) {
                fill.style.width = "100%";
                status.textContent = `✓ ជោគជ័យ (បានចូលក្នុង ${driveLabel})`;
                status.style.color = "#10b981";
            } else {
                status.textContent = "✕ បរាជ័យ: " + (result.error || "Error");
                status.style.color = "#f43f5e";
            }
        } catch (err) {
            item.querySelector(".status-txt").textContent = "✕ Error: " + err.message;
        }
    }

    // If uploading to different drive, switch to it
    if (currentCategory !== driveToUse) {
        currentCategory = driveToUse;
        currentFolderId = null;
        folderStack = [];
        document.querySelectorAll(".nav-item").forEach(b => {
            b.classList.toggle("active", b.dataset.cat === driveToUse);
        });
    }
    updateCurrentDriveHeader();
    fetchStats();
    loadFiles();
}

function downloadFile(id) {
    window.location.href = `/api/download/${id}`;
}

function updateCurrentDriveHeader() {
    const isTrash = currentCategory === "trash";
    const uploadBtn = document.getElementById("btnUploadFile");
    const emptyTrashBtn = document.getElementById("btnEmptyTrash");
    if (uploadBtn) uploadBtn.style.display = isTrash ? "none" : "flex";
    if (emptyTrashBtn) emptyTrashBtn.style.display = isTrash ? "flex" : "none";

    const titleEl = document.getElementById("currentDriveTitle");
    const dropHint = document.getElementById("tDropHint");

    if (currentCategory === "vuochlin") {
        if (titleEl) titleEl.textContent = "NEANG VUOCHLIN";
        if (dropHint) dropHint.textContent = currentLang === "km" 
            ? "ទម្លាក់ឯកសារនៅទីនេះដើម្បីផ្ទុកចូល Drive [NEANG VUOCHLIN]"
            : "Drop files here to upload to Drive [NEANG VUOCHLIN]";
    } else if (currentCategory === "mercy") {
        if (titleEl) titleEl.textContent = "Mercy Dental Care";
        if (dropHint) dropHint.textContent = currentLang === "km" 
            ? "ទម្លាក់ឯកសារនៅទីនេះដើម្បីផ្ទុកចូល Drive [Mercy Dental Care]"
            : "Drop files here to upload to Drive [Mercy Dental Care]";
    } else if (currentCategory === "trash") {
        if (titleEl) titleEl.textContent = currentLang === "km" ? "ធុងសំរាម (Trash)" : "Recycle Bin";
    } else {
        if (titleEl) titleEl.textContent = "HUN BUNTHA";
        if (dropHint) dropHint.textContent = currentLang === "km"
            ? "ទម្លាក់ឯកសារនៅទីនេះដើម្បីផ្ទុកចូល Drive [HUN BUNTHA]"
            : "Drop files here to upload to Drive [HUN BUNTHA]";
    }
}

function previewFile(id) {
    const file = filesData.find(f => f.id === id);
    if (!file) return;

    const modal = document.getElementById("previewModal");
    const body = document.getElementById("previewModalBody");
    const nameEl = document.getElementById("previewFileName");
    const iconEl = document.getElementById("previewFileIcon");
    const dlBtn = document.getElementById("btnPreviewDownload");
    const newTabBtn = document.getElementById("btnPreviewNewTab");

    if (nameEl) nameEl.textContent = file.file_name;
    if (iconEl) iconEl.textContent = getFileIcon(file.category);
    if (dlBtn) dlBtn.onclick = () => downloadFile(file.id);

    const ext = file.file_name.toLowerCase().split('.').pop();
    const viewUrl = `/api/view/${file.id}`;

    if (newTabBtn) {
        newTabBtn.href = viewUrl;
    }

    // Supported preview types
    const imageExts = ['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'bmp', 'ico'];
    const videoExts = ['mp4', 'webm', 'ogg', 'mov', 'm4v'];
    const audioExts = ['mp3', 'wav', 'ogg', 'm4a', 'aac', 'flac'];
    const isPdf = ext === 'pdf';
    const textExts = ['txt', 'log', 'csv', 'json', 'md', 'html', 'xml', 'js', 'py', 'css', 'sql', 'sh', 'bat'];

    body.innerHTML = `<div class="preview-loading">⏳ កំពុងទាញយកមកបើកមើល... (Loading preview...)</div>`;
    modal.style.display = "flex";

    if (imageExts.includes(ext)) {
        body.innerHTML = `
            <div class="preview-media-container">
                <img src="${viewUrl}" alt="${file.file_name}" class="preview-img" onerror="this.parentElement.innerHTML='<div class=\\'preview-error\\'>មិនអាចបើកមើលរូបភាពនេះបានទេ</div>'">
            </div>
        `;
    } else if (videoExts.includes(ext)) {
        body.innerHTML = `
            <div class="preview-media-container">
                <video controls autoplay class="preview-video">
                    <source src="${viewUrl}">
                    Browser របស់អ្នកមិនគាំទ្រការចាក់វីដេអូនេះទេ។
                </video>
            </div>
        `;
    } else if (audioExts.includes(ext)) {
        body.innerHTML = `
            <div class="preview-audio-container">
                <div class="preview-audio-icon">🎵</div>
                <div class="preview-audio-title">${file.file_name}</div>
                <audio controls autoplay style="width: 100%; max-width: 420px; margin-top: 18px;">
                    <source src="${viewUrl}">
                </audio>
            </div>
        `;
    } else if (isPdf) {
        body.innerHTML = `
            <div class="preview-pdf-container">
                <iframe src="${viewUrl}" class="preview-iframe" title="${file.file_name}"></iframe>
            </div>
        `;
    } else if (textExts.includes(ext)) {
        fetch(viewUrl)
            .then(res => {
                if (!res.ok) throw new Error("Status " + res.status);
                return res.text();
            })
            .then(txt => {
                const escaped = txt.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
                body.innerHTML = `<pre class="preview-text-content"><code>${escaped}</code></pre>`;
            })
            .catch(err => {
                body.innerHTML = `<div class="preview-error">បរាជ័យក្នុងការបើកអត្ថបទ: ${err.message}</div>`;
            });
    } else {
        body.innerHTML = `
            <div class="preview-generic-container">
                <div class="generic-icon">${getFileIcon(file.category)}</div>
                <div class="generic-name">${file.file_name}</div>
                <div class="generic-size">${formatSize(file.file_size)}</div>
                <p style="color: var(--text-muted); font-size: 13px; margin: 15px 0;">ប្រភេទ File នេះត្រូវទាញយកមកបើកក្នុងកុំព្យូទ័រ ឬទូរស័ព្ទដៃ</p>
                <div style="display: flex; gap: 10px; justify-content: center; flex-wrap: wrap;">
                    <a href="${viewUrl}" target="_blank" class="btn-primary" style="text-decoration: none; padding: 8px 16px;">🌐 បើកក្នុង Tab ថ្មី (Open in Tab)</a>
                    <button class="btn-secondary" onclick="downloadFile(${file.id})" style="padding: 8px 16px;">📥 ទាញយក (Download)</button>
                </div>
            </div>
        `;
    }
}

async function toggleFavorite(id) {
    await fetch(`/api/favorite/${id}`, { method: "POST" });
    loadFiles();
}

async function trashFile(id) {
    await fetch(`/api/trash/${id}`, { method: "POST" });
    fetchStats();
    loadFiles();
}

async function restoreFile(id) {
    await fetch(`/api/restore/${id}`, { method: "POST" });
    fetchStats();
    loadFiles();
}

async function deletePermanent(id) {
    if (confirm("ឯកសារនេះនឹងត្រូវលុបជាអចិន្ត្រៃយ៍! តើអ្នកប្រាកដទេ?")) {
        await fetch(`/api/delete-permanent/${id}`, { method: "DELETE" });
        fetchStats();
        loadFiles();
    }
}

// Settings (Password Security only)
async function fetchSettings() {
    try {
        const res = await fetch("/api/settings");
        const data = await res.json();
        if (data.settings) {
            const setVal = (id, v) => {
                const el = document.getElementById(id);
                if (el) el.value = v;
            };
            setVal("cfgSitePassword", data.settings.website_password || "1234");
            setVal("cfgPwdBuntha", data.settings.password_buntha || "1111");
            setVal("cfgPwdVuochlin", data.settings.password_vuochlin || "2222");
            setVal("cfgPwdMercy", data.settings.password_mercy || "3333");
        }
    } catch (e) {
        console.error("fetchSettings error:", e);
    }
}

async function testTelegramConnection() {
    // Legacy helper kept for backward safety
}

async function saveSettingsToServer() {
    const payload = {
        website_password: document.getElementById("cfgSitePassword")?.value.trim() || "1234",
        password_buntha: document.getElementById("cfgPwdBuntha")?.value.trim() || "1111",
        password_vuochlin: document.getElementById("cfgPwdVuochlin")?.value.trim() || "2222",
        password_mercy: document.getElementById("cfgPwdMercy")?.value.trim() || "3333"
    };

    const btnSave = document.getElementById("btnSaveSettings");
    if (btnSave) {
        btnSave.disabled = true;
        btnSave.textContent = "កំពុងរក្សាទុក...";
    }

    try {
        const res = await fetch("/api/settings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (data.success) {
            document.getElementById("settingsModal").style.display = "none";
            alert("✅ បានរក្សាទុកការកំណត់លេខកូដសម្ងាត់ជោគជ័យ!");
            fetchStats();
            loadFiles();
        } else {
            alert("❌ បរាជ័យក្នុងការរក្សាទុក!");
        }
    } catch (e) {
        alert("❌ Error: " + e.message);
    } finally {
        if (btnSave) {
            btnSave.disabled = false;
            btnSave.textContent = "រក្សាទុកការកំណត់";
        }
    }
}

function applyLanguage() {
    const t = i18n[currentLang];
    const setTxt = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.textContent = val;
    };
    setTxt("tAllFiles", t.all_files);
    setTxt("tDocuments", t.documents);
    setTxt("tImages", t.images);
    setTxt("tVideos", t.videos);
    setTxt("tMusic", t.music);
    setTxt("tArchives", t.archives);
    setTxt("tFavorites", t.favorites);
    setTxt("tTrash", t.trash);
    setTxt("tQuotaTitle", t.quota_title);
    setTxt("tUploadFile", t.upload_file);
    setTxt("tEmptyTrash", t.empty_trash);
    const searchEl = document.getElementById("searchInput");
    if (searchEl) searchEl.placeholder = t.search_placeholder;
    setTxt("tDropHint", t.drop_hint);
    setTxt("tNoFiles", t.no_files);
    setTxt("btnLangToggle", t.lang_btn);
    fetchStats();
    renderFiles();
}

/* ==========================================================================
   Windows 11 Context Menus & Folder Handlers
   ========================================================================== */
function initContextMenuListeners() {
    const dropZone = document.getElementById("dropZone");

    // Right Click on dropZone (empty area / viewport)
    if (dropZone) {
        dropZone.addEventListener("contextmenu", (e) => {
            // If right-clicked on an interactive child or folder/file card, ignore here (card handles it)
            if (e.target.closest(".folder-card") || e.target.closest(".file-card") || e.target.closest("tr") || e.target.closest("button") || e.target.closest("input") || e.target.closest("a")) {
                return;
            }
            e.preventDefault();
            showBgContextMenu(e.clientX, e.clientY);
        });
    }

    // Top New Folder button in address bar
    const btnNewFolderTop = document.getElementById("btnNewFolderTop");
    if (btnNewFolderTop) {
        btnNewFolderTop.addEventListener("click", () => {
            promptNewFolder();
        });
    }

    // Context menu: New > Folder
    const cmenuNewFolder = document.getElementById("cmenuNewFolder");
    if (cmenuNewFolder) {
        cmenuNewFolder.addEventListener("click", () => {
            promptNewFolder();
        });
    }

    // Context menu: Upload
    const cmenuUpload = document.getElementById("cmenuUpload");
    if (cmenuUpload) {
        cmenuUpload.addEventListener("click", () => {
            hideAllContextMenus();
            const fileInput = document.getElementById("fileInput");
            if (fileInput) fileInput.click();
        });
    }

    // Context menu: Refresh
    const cmenuRefresh = document.getElementById("cmenuRefresh");
    if (cmenuRefresh) {
        cmenuRefresh.addEventListener("click", () => {
            hideAllContextMenus();
            fetchStats();
            loadFiles();
        });
    }

    // Folder Context Menu: Open
    const fcmenuOpen = document.getElementById("fcmenuOpen");
    if (fcmenuOpen) {
        fcmenuOpen.addEventListener("click", () => {
            hideAllContextMenus();
            if (activeContextItem && activeContextItem.type === "folder") {
                openFolder(activeContextItem.id, activeContextItem.name);
            }
        });
    }

    // Folder Context Menu: Rename
    const fcmenuRename = document.getElementById("fcmenuRename");
    if (fcmenuRename) {
        fcmenuRename.addEventListener("click", () => {
            hideAllContextMenus();
            if (activeContextItem && activeContextItem.type === "folder") {
                const fId = activeContextItem.id;
                showPromptModal(
                    currentLang === "km" ? "ប្តូរឈ្មោះថត (Rename Folder)" : "Rename Folder",
                    currentLang === "km" ? "ឈ្មោះថតថ្មី៖" : "New Folder Name:",
                    activeContextItem.name,
                    async (newName) => {
                        await fetch("/api/folders/rename", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ folder_id: fId, name: newName })
                        });
                        loadFiles();
                    }
                );
            }
        });
    }

    // Folder Context Menu: Delete
    const fcmenuDelete = document.getElementById("fcmenuDelete");
    if (fcmenuDelete) {
        fcmenuDelete.addEventListener("click", async () => {
            hideAllContextMenus();
            if (activeContextItem && activeContextItem.type === "folder") {
                const confirmMsg = currentLang === "km" 
                    ? `តើអ្នកពិតជាចង់លុបថត "${activeContextItem.name}" និងឯកសារទាំងអស់ក្នុងនោះមែនទេ?`
                    : `Are you sure you want to delete folder "${activeContextItem.name}" and all its contents?`;
                if (confirm(confirmMsg)) {
                    await fetch("/api/folders/delete", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ folder_id: activeContextItem.id })
                    });
                    loadFiles();
                }
            }
        });
    }

    // File Context Menu: View
    const filecmenuView = document.getElementById("filecmenuView");
    if (filecmenuView) {
        filecmenuView.addEventListener("click", () => {
            hideAllContextMenus();
            if (activeContextItem && activeContextItem.type === "file") {
                previewFile(activeContextItem.id);
            }
        });
    }

    // File Context Menu: Download
    const filecmenuDownload = document.getElementById("filecmenuDownload");
    if (filecmenuDownload) {
        filecmenuDownload.addEventListener("click", () => {
            hideAllContextMenus();
            if (activeContextItem && activeContextItem.type === "file") {
                downloadFile(activeContextItem.id);
            }
        });
    }

    // File Context Menu: Rename
    const filecmenuRename = document.getElementById("filecmenuRename");
    if (filecmenuRename) {
        filecmenuRename.addEventListener("click", () => {
            hideAllContextMenus();
            if (activeContextItem && activeContextItem.type === "file") {
                const fId = activeContextItem.id;
                showPromptModal(
                    currentLang === "km" ? "ប្តូរឈ្មោះឯកសារ (Rename File)" : "Rename File",
                    currentLang === "km" ? "ឈ្មោះឯកសារថ្មី៖" : "New File Name:",
                    activeContextItem.name,
                    async (newName) => {
                        await fetch("/api/files/rename", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ file_id: fId, name: newName })
                        });
                        loadFiles();
                    }
                );
            }
        });
    }

    // File Context Menu: Delete
    const filecmenuDelete = document.getElementById("filecmenuDelete");
    if (filecmenuDelete) {
        filecmenuDelete.addEventListener("click", () => {
            hideAllContextMenus();
            if (activeContextItem && activeContextItem.type === "file") {
                trashFile(activeContextItem.id);
            }
        });
    }

    // Dismiss context menus on click outside
    window.addEventListener("click", (e) => {
        if (!e.target.closest(".win-context-menu")) {
            hideAllContextMenus();
        }
    });

    // Dismiss context menus on Escape key or scroll
    window.addEventListener("keydown", (e) => {
        if (e.key === "Escape") {
            hideAllContextMenus();
        }
    });
    window.addEventListener("scroll", hideAllContextMenus, true);
}

function hideAllContextMenus() {
    const bgMenu = document.getElementById("bgContextMenu");
    const folderMenu = document.getElementById("folderContextMenu");
    const fileMenu = document.getElementById("fileContextMenu");
    if (bgMenu) bgMenu.style.display = "none";
    if (folderMenu) folderMenu.style.display = "none";
    if (fileMenu) fileMenu.style.display = "none";
}

function positionMenu(menu, x, y) {
    menu.style.display = "block";
    const rect = menu.getBoundingClientRect();
    const winWidth = window.innerWidth;
    const winHeight = window.innerHeight;

    let posX = x;
    let posY = y;

    if (posX + rect.width > winWidth - 10) {
        posX = winWidth - rect.width - 10;
    }
    if (posY + rect.height > winHeight - 10) {
        posY = winHeight - rect.height - 10;
    }

    menu.style.left = `${Math.max(10, posX)}px`;
    menu.style.top = `${Math.max(10, posY)}px`;
}

function showBgContextMenu(x, y) {
    hideAllContextMenus();
    const menu = document.getElementById("bgContextMenu");
    if (menu) positionMenu(menu, x, y);
}

function showFolderContextMenu(x, y, folder) {
    hideAllContextMenus();
    activeContextItem = { type: 'folder', id: folder.id, name: folder.folder_name };
    const menu = document.getElementById("folderContextMenu");
    if (menu) positionMenu(menu, x, y);
}

function showFileContextMenu(x, y, file) {
    hideAllContextMenus();
    activeContextItem = { type: 'file', id: file.id, name: file.file_name, is_trash: file.is_trash };
    const menu = document.getElementById("fileContextMenu");
    if (menu) positionMenu(menu, x, y);
}

function promptNewFolder() {
    hideAllContextMenus();
    showPromptModal(
        currentLang === "km" ? "បង្កើតថតថ្មី (New Folder)" : "Create New Folder",
        currentLang === "km" ? "ឈ្មោះថតឯកសារ៖" : "Folder Name:",
        "New folder",
        async (folderName) => {
            const drive = currentCategory === "vuochlin" ? "vuochlin" : "buntha";
            const res = await fetch("/api/folders/create", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    name: folderName,
                    drive: drive,
                    parent_id: currentFolderId
                })
            });
            const data = await res.json();
            if (data.success) {
                loadFiles();
            }
        }
    );
}

function promptRenameFolder(folderId, currentName) {
    hideAllContextMenus();
    showPromptModal(
        currentLang === "km" ? "ប្តូរឈ្មោះថត (Rename Folder)" : "Rename Folder",
        currentLang === "km" ? "ឈ្មោះថតថ្មី៖" : "New Folder Name:",
        currentName,
        async (newName) => {
            if (!newName || newName === currentName) return;
            await fetch("/api/folders/rename", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ folder_id: folderId, name: newName })
            });
            loadFiles();
        }
    );
}

function promptRenameFile(fileId, currentName) {
    hideAllContextMenus();
    showPromptModal(
        currentLang === "km" ? "ប្តូរឈ្មោះឯកសារ (Rename File)" : "Rename File",
        currentLang === "km" ? "ឈ្មោះឯកសារថ្មី៖" : "New File Name:",
        currentName,
        async (newName) => {
            if (!newName || newName === currentName) return;
            await fetch("/api/files/rename", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ file_id: fileId, name: newName })
            });
            loadFiles();
        }
    );
}

async function confirmDeleteFolder(folderId, folderName) {
    hideAllContextMenus();
    const confirmMsg = currentLang === "km" 
        ? `តើអ្នកពិតជាចង់លុបថត "${folderName}" និងឯកសារទាំងអស់ក្នុងនោះមែនទេ?`
        : `Are you sure you want to delete folder "${folderName}" and all its contents?`;
    if (confirm(confirmMsg)) {
        await fetch("/api/folders/delete", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ folder_id: folderId })
        });
        loadFiles();
    }
}

async function emptyTrash() {
    hideAllContextMenus();
    const confirmMsg = currentLang === "km" 
        ? "តើអ្នកពិតជាចង់សម្អាតធុងសំរាមមែនទេ? (Empty trash permanently?)"
        : "Are you sure you want to empty the recycle bin permanently?";
    if (confirm(confirmMsg)) {
        await fetch("/api/empty-trash", { method: "POST" });
        fetchStats();
        loadFiles();
    }
}

function showPromptModal(title, label, defaultValue, onConfirm) {
    const modal = document.getElementById("promptModal");
    const titleEl = document.getElementById("promptModalTitle");
    const labelEl = document.getElementById("promptModalLabel");
    const inputEl = document.getElementById("promptModalInput");
    const confirmBtn = document.getElementById("btnConfirmPrompt");
    const cancelBtn = document.getElementById("btnCancelPrompt");
    const closeBtn = document.getElementById("btnClosePrompt");

    if (titleEl) titleEl.textContent = title;
    if (labelEl) labelEl.textContent = label;
    if (inputEl) {
        inputEl.value = defaultValue || "";
    }

    modal.style.display = "flex";
    setTimeout(() => {
        if (inputEl) {
            inputEl.focus();
            inputEl.select();
        }
    }, 50);

    const handleConfirm = () => {
        const val = inputEl ? inputEl.value.trim() : "";
        if (!val) return;
        modal.style.display = "none";
        cleanup();
        onConfirm(val);
    };

    const handleCancel = () => {
        modal.style.display = "none";
        cleanup();
    };

    const handleKeyDown = (e) => {
        if (e.key === "Enter") {
            e.preventDefault();
            handleConfirm();
        } else if (e.key === "Escape") {
            e.preventDefault();
            handleCancel();
        }
    };

    function cleanup() {
        confirmBtn.removeEventListener("click", handleConfirm);
        cancelBtn.removeEventListener("click", handleCancel);
        closeBtn.removeEventListener("click", handleCancel);
        if (inputEl) inputEl.removeEventListener("keydown", handleKeyDown);
    }

    confirmBtn.addEventListener("click", handleConfirm);
    cancelBtn.addEventListener("click", handleCancel);
    closeBtn.addEventListener("click", handleCancel);
    if (inputEl) inputEl.addEventListener("keydown", handleKeyDown);
}

/* ==========================================================================
   Windows 11 Rubberband / Marquee Drag-Selection Logic
   ========================================================================== */
function initMarqueeSelection() {
    const dropZone = document.getElementById("dropZone");
    if (!dropZone) return;

    // Create marquee element once
    let marquee = document.getElementById("selectionMarqueeBox");
    if (!marquee) {
        marquee = document.createElement("div");
        marquee.id = "selectionMarqueeBox";
        marquee.className = "selection-marquee";
        document.body.appendChild(marquee);
    }

    let isMouseDown = false;
    let isSelecting = false;
    let startX = 0;
    let startY = 0;
    let initialSelectedFiles = new Set();
    let initialSelectedFolders = new Set();

    dropZone.addEventListener("mousedown", (e) => {
        // Only trigger on primary left click
        if (e.button !== 0) return;

        // If clicking on an interactive element or directly on a card/row item, ignore
        if (e.target.closest("button") ||
            e.target.closest("input") ||
            e.target.closest("a") ||
            e.target.closest(".row-actions") ||
            e.target.closest(".win-context-menu") ||
            e.target.closest(".selection-floating-bar") ||
            e.target.closest(".modal-backdrop") ||
            e.target.closest(".win-nav-bar") ||
            e.target.closest(".win-command-bar") ||
            e.target.closest(".win-tabs-bar")) {
            return;
        }

        // If clicking inside table body on a specific row cell, check if row was clicked
        if (e.target.closest("tr.win-row") || e.target.closest(".win-item-card")) {
            return;
        }

        isMouseDown = true;
        isSelecting = false;
        startX = e.clientX;
        startY = e.clientY;

        if (e.ctrlKey || e.metaKey || e.shiftKey) {
            initialSelectedFiles = new Set(selectedFileIds);
            initialSelectedFolders = new Set(selectedFolderIds);
        } else {
            initialSelectedFiles = new Set();
            initialSelectedFolders = new Set();
            clearSelection();
        }
    });

    window.addEventListener("mousemove", (e) => {
        if (!isMouseDown) return;

        const currentX = e.clientX;
        const currentY = e.clientY;
        const diffX = currentX - startX;
        const diffY = currentY - startY;

        // Threshold to distinguish click from drag
        if (!isSelecting && (Math.abs(diffX) > 4 || Math.abs(diffY) > 4)) {
            isSelecting = true;
            document.body.classList.add("marquee-selecting");
            marquee.style.display = "block";
        }

        if (!isSelecting) return;

        // Calculate rectangle boundaries
        const left = Math.min(startX, currentX);
        const top = Math.min(startY, currentY);
        const width = Math.abs(diffX);
        const height = Math.abs(diffY);

        marquee.style.left = `${left}px`;
        marquee.style.top = `${top}px`;
        marquee.style.width = `${width}px`;
        marquee.style.height = `${height}px`;

        const marqueeRect = {
            left: left,
            top: top,
            right: left + width,
            bottom: top + height
        };

        const newlySelectedFiles = new Set(initialSelectedFiles);
        const newlySelectedFolders = new Set(initialSelectedFolders);

        // Check Windows 11 Details Table Rows
        document.querySelectorAll(".win-details-table tbody tr").forEach(tr => {
            const fileId = parseInt(tr.dataset.fileId);
            const folderId = parseInt(tr.dataset.folderId);
            const rect = tr.getBoundingClientRect();
            const intersects = !(
                rect.right < marqueeRect.left ||
                rect.left > marqueeRect.right ||
                rect.bottom < marqueeRect.top ||
                rect.top > marqueeRect.bottom
            );

            if (fileId) {
                if (intersects) newlySelectedFiles.add(fileId);
                else if (!initialSelectedFiles.has(fileId)) newlySelectedFiles.delete(fileId);
            } else if (folderId) {
                if (intersects) newlySelectedFolders.add(folderId);
                else if (!initialSelectedFolders.has(folderId)) newlySelectedFolders.delete(folderId);
            }
        });

        // Check Windows 11 Icon View Cards
        document.querySelectorAll(".win-items-view .win-item-card").forEach(card => {
            const fileId = parseInt(card.dataset.fileId);
            const folderId = parseInt(card.dataset.folderId);
            const rect = card.getBoundingClientRect();
            const intersects = !(
                rect.right < marqueeRect.left ||
                rect.left > marqueeRect.right ||
                rect.bottom < marqueeRect.top ||
                rect.top > marqueeRect.bottom
            );

            if (fileId) {
                if (intersects) newlySelectedFiles.add(fileId);
                else if (!initialSelectedFiles.has(fileId)) newlySelectedFiles.delete(fileId);
            } else if (folderId) {
                if (intersects) newlySelectedFolders.add(folderId);
                else if (!initialSelectedFolders.has(folderId)) newlySelectedFolders.delete(folderId);
            }
        });

        selectedFileIds = newlySelectedFiles;
        selectedFolderIds = newlySelectedFolders;
        updateSelectionUI();
    });

    window.addEventListener("mouseup", (e) => {
        if (!isMouseDown) return;
        isMouseDown = false;

        if (isSelecting) {
            isSelecting = false;
            document.body.classList.remove("marquee-selecting");
            marquee.style.display = "none";
            updateSelectionUI();
        }
    });
}


