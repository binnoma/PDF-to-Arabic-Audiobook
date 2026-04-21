document.addEventListener('DOMContentLoaded', () => {
    const pdfUploadArea = document.getElementById('pdf-upload-area');
    const pdfFileInput = document.getElementById('pdf-file');
    const pdfFileInfo = document.getElementById('pdf-file-info');
    const extractBtn = document.getElementById('extract-btn');

    const refUploadArea = document.getElementById('ref-upload-area');
    const refFileInput = document.getElementById('ref-file');
    const refFileInfo = document.getElementById('ref-file-info');
    const convertBtn = document.getElementById('convert-btn');

    const step1 = document.getElementById('step-1');
    const step2 = document.getElementById('step-2');
    const step3 = document.getElementById('step-3');
    const loadingOverlay = document.getElementById('loading-overlay');
    const extractedText = document.getElementById('extracted-text');

    const progressContainer = document.getElementById('progress-container');
    const resultContainer = document.getElementById('result-container');
    const errorContainer = document.getElementById('error-container');
    const progressBar = document.getElementById('progress-bar');
    const progressText = document.getElementById('progress-text');
    const downloadBtn = document.getElementById('download-btn');
    const errorMsg = document.getElementById('error-msg');
    const previewBtn = document.getElementById('preview-btn');
    const readingSpeed = document.getElementById('reading-speed');

    const voicesContainer = document.getElementById('voices-container');
    let currentPdfFile = null;
    let currentRefFile = null;
    let selectedVoiceId = null;

    // --- Voice Library Logic ---
    async function fetchVoices() {
        try {
            const response = await fetch('/get_voices');
            const voices = await response.json();
            renderVoices(voices);
        } catch (error) {
            console.error("Error fetching voices", error);
            voicesContainer.innerHTML = '<p class="error">فشل تحميل مكتبة الأصوات</p>';
        }
    }

    function renderVoices(voices) {
        voicesContainer.innerHTML = '';
        
        voices.forEach(voice => {
            const card = document.createElement('div');
            card.className = 'voice-card';
            card.innerHTML = `<i class="fas fa-user"></i> <span>${voice.name}</span>`;
            card.onclick = () => selectVoice(voice.id, card);
            voicesContainer.appendChild(card);
        });

        if (voices.length === 0) {
            voicesContainer.innerHTML = '<p style="grid-column: 1/-1; text-align: center; color: #64748b;">لا توجد أصوات جاهزة حالياً. يمكنك رفع صوتك الخاص بالأسفل.</p>';
        }
    }

    function selectVoice(id, card) {
        document.querySelectorAll('.voice-card').forEach(c => c.classList.remove('selected'));
        
        if (selectedVoiceId === id) {
            selectedVoiceId = null;
        } else {
            selectedVoiceId = id;
            card.classList.add('selected');
            // Clear uploaded file if library voice is picked
            currentRefFile = null;
            refFileInfo.classList.add('hidden');
        }
        checkConvertReady();
    }

    fetchVoices();

    // --- File Upload Handlers ---
    function handleDragOver(e) {
        e.preventDefault();
        e.currentTarget.classList.add('dragover');
    }

    function handleDragLeave(e) {
        e.preventDefault();
        e.currentTarget.classList.remove('dragover');
    }

    // PDF Upload
    pdfUploadArea.addEventListener('click', () => pdfFileInput.click());
    pdfUploadArea.addEventListener('dragover', handleDragOver);
    pdfUploadArea.addEventListener('dragleave', handleDragLeave);
    pdfUploadArea.addEventListener('drop', (e) => {
        e.preventDefault();
        pdfUploadArea.classList.remove('dragover');
        if (e.dataTransfer.files.length) {
            handlePdfFile(e.dataTransfer.files[0]);
        }
    });
    pdfFileInput.addEventListener('change', (e) => {
        if (e.target.files.length) handlePdfFile(e.target.files[0]);
    });

    function handlePdfFile(file) {
        if (file.type !== "application/pdf") {
            alert("الرجاء اختيار ملف PDF");
            return;
        }
        currentPdfFile = file;
        pdfFileInfo.innerHTML = `<i class="fas fa-file-pdf"></i> ${file.name}`;
        pdfFileInfo.classList.remove('hidden');
        extractBtn.disabled = false;
    }

    // Reference Audio Upload
    refUploadArea.addEventListener('click', () => refFileInput.click());
    refUploadArea.addEventListener('dragover', handleDragOver);
    refUploadArea.addEventListener('dragleave', handleDragLeave);
    refUploadArea.addEventListener('drop', (e) => {
        e.preventDefault();
        refUploadArea.classList.remove('dragover');
        if (e.dataTransfer.files.length) {
            handleRefFile(e.dataTransfer.files[0]);
        }
    });
    refFileInput.addEventListener('change', (e) => {
        if (e.target.files.length) handleRefFile(e.target.files[0]);
    });

    function handleRefFile(file) {
        if (!file.type.startsWith("audio/")) {
            alert("الرجاء اختيار ملف صوتي");
            return;
        }
        currentRefFile = file;
        refFileInfo.innerHTML = `<i class="fas fa-file-audio"></i> ${file.name}`;
        refFileInfo.classList.remove('hidden');
        // Deselect library voice if user uploads custom
        selectedVoiceId = null;
        document.querySelectorAll('.voice-card').forEach(c => c.classList.remove('selected'));
        checkConvertReady();
    }

    function checkConvertReady() {
        const hasVoice = selectedVoiceId || currentRefFile;
        const hasText = extractedText.value.trim().length > 0;
        if (hasVoice && hasText) {
            convertBtn.disabled = false;
            previewBtn.disabled = false;
        } else {
            convertBtn.disabled = true;
            previewBtn.disabled = true;
        }
    }

    extractedText.addEventListener('input', checkConvertReady);

    // --- Actions ---
    extractBtn.addEventListener('click', async () => {
        if (!currentPdfFile) return;

        const formData = new FormData();
        formData.append('pdf', currentPdfFile);

        extractBtn.disabled = true;
        loadingOverlay.classList.remove('hidden');

        try {
            const response = await fetch('/extract_text', {
                method: 'POST',
                body: formData
            });
            const data = await response.json();

            if (response.ok) {
                extractedText.value = data.text;
                step1.classList.add('hidden');
                step2.classList.remove('hidden');
                checkConvertReady();
            } else {
                alert(data.error || "فشل استخراج النص");
                extractBtn.disabled = false;
            }
        } catch (error) {
            alert("حدث خطأ في الاتصال بالخادم");
            extractBtn.disabled = false;
        } finally {
            loadingOverlay.classList.add('hidden');
        }
    });

    // Convert to Audio (General Function)
    async function startConversion(isPreview = false) {
        const text = extractedText.value.trim();
        if (!text || (!selectedVoiceId && !currentRefFile)) return;

        const formData = new FormData();
        formData.append('text', text);
        formData.append('preview', isPreview);
        formData.append('speed', readingSpeed.value);
        
        if (selectedVoiceId) {
            formData.append('voice_key', selectedVoiceId);
        } else {
            formData.append('voice_key', 'custom');
            formData.append('reference_audio', currentRefFile);
        }

        step2.classList.add('hidden');
        step3.classList.remove('hidden');
        progressContainer.classList.remove('hidden');
        resultContainer.classList.add('hidden');
        errorContainer.classList.add('hidden');

        try {
            const response = await fetch('/generate_audio', {
                method: 'POST',
                body: formData
            });
            const data = await response.json();

            if (response.ok) {
                pollProgress(data.task_id);
            } else {
                showError(data.error || "حدث خطأ في بدء عملية التحويل");
            }
        } catch (error) {
            showError("حدث خطأ في الاتصال بالخادم");
        }
    }

    convertBtn.addEventListener('click', () => startConversion(false));
    previewBtn.addEventListener('click', () => startConversion(true));


    function pollProgress(taskId) {
        const interval = setInterval(async () => {
            try {
                const response = await fetch(`/progress/${taskId}`);
                const data = await response.json();

                if (data.status === 'processing') {
                    progressBar.style.width = `${data.progress}%`;
                    progressText.innerText = `${data.progress}% - ${data.message}`;
                } else if (data.status === 'completed') {
                    clearInterval(interval);
                    progressBar.style.width = `100%`;
                    progressText.innerText = `100% - ${data.message}`;
                    
                    setTimeout(() => {
                        progressContainer.classList.add('hidden');
                        resultContainer.classList.remove('hidden');
                        downloadBtn.href = `/download/${taskId}`;
                    }, 1000);
                } else if (data.status === 'failed') {
                    clearInterval(interval);
                    showError(data.error || "فشلت عملية التحويل");
                }
            } catch (error) {
                console.error("Error polling progress", error);
            }
        }, 1500);
    }

    function showError(message) {
        progressContainer.classList.add('hidden');
        errorContainer.classList.remove('hidden');
        errorMsg.innerText = message;
    }
});
