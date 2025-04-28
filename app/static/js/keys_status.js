// 统计数据可视化交互效果

function copyToClipboard(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
        return navigator.clipboard.writeText(text);
    } else {
        return new Promise((resolve, reject) => {
            const textArea = document.createElement("textarea");
            textArea.value = text;
            textArea.style.position = "fixed";
            document.body.appendChild(textArea);
            textArea.focus();
            textArea.select();
            try {
                const successful = document.execCommand('copy');
                document.body.removeChild(textArea);
                if (successful) {
                    resolve();
                } else {
                    reject(new Error('复制失败'));
                }
            } catch (err) {
                document.body.removeChild(textArea);
                reject(err);
            }
        });
    }
}

// 添加统计项动画效果
function initStatItemAnimations() {
    const statItems = document.querySelectorAll('.stat-item');
    statItems.forEach(item => {
        item.addEventListener('mouseenter', () => {
            item.style.transform = 'scale(1.05)';
            const icon = item.querySelector('.stat-icon');
            if (icon) {
                icon.style.opacity = '0.2';
                icon.style.transform = 'scale(1.1) rotate(0deg)';
            }
        });

        item.addEventListener('mouseleave', () => {
            item.style.transform = '';
            const icon = item.querySelector('.stat-icon');
            if (icon) {
                icon.style.opacity = '';
                icon.style.transform = '';
            }
        });
    });
}

// 获取指定类型区域内选中的密钥
function getSelectedKeys(type) {
    const checkboxes = document.querySelectorAll(`#${type}Keys .key-checkbox:checked`);
    return Array.from(checkboxes).map(cb => cb.value);
}

// 更新指定类型区域的批量操作按钮状态和计数
function updateBatchActions(type) {
    const selectedKeys = getSelectedKeys(type);
    const count = selectedKeys.length;
    const batchActionsDiv = document.getElementById(`${type}BatchActions`);
    const selectedCountSpan = document.getElementById(`${type}SelectedCount`);
    const buttons = batchActionsDiv.querySelectorAll('button');

    if (count > 0) {
        batchActionsDiv.classList.remove('hidden');
        selectedCountSpan.textContent = count;
        buttons.forEach(button => button.disabled = false);
    } else {
        batchActionsDiv.classList.add('hidden');
        selectedCountSpan.textContent = '0';
        buttons.forEach(button => button.disabled = true);
    }

    // 更新全选复选框状态
    const selectAllCheckbox = document.getElementById(`selectAll${type.charAt(0).toUpperCase() + type.slice(1)}`);
    const allCheckboxes = document.querySelectorAll(`#${type}Keys .key-checkbox`);
    // 只有在有可见的 key 时才考虑全选状态
    const visibleCheckboxes = document.querySelectorAll(`#${type}Keys li:not([style*="display: none"]) .key-checkbox`);
    if (selectAllCheckbox && visibleCheckboxes.length > 0) {
        selectAllCheckbox.checked = count === visibleCheckboxes.length;
        selectAllCheckbox.indeterminate = count > 0 && count < visibleCheckboxes.length;
    } else if (selectAllCheckbox) {
        selectAllCheckbox.checked = false;
        selectAllCheckbox.indeterminate = false;
    }
}

// 全选/取消全选指定类型的密钥
function toggleSelectAll(type, isChecked) {
    const checkboxes = document.querySelectorAll(`#${type}Keys li:not([style*="display: none"]) .key-checkbox`); // 只选择可见的
    checkboxes.forEach(checkbox => {
        checkbox.checked = isChecked;
    });
    updateBatchActions(type);
}

// 复制选中的密钥
function copySelectedKeys(type) {
    const selectedKeys = getSelectedKeys(type);

    if (selectedKeys.length === 0) {
        showNotification('没有选中的密钥可复制', 'warning');
        return;
    }

    const keysText = selectedKeys.join('\n');

    copyToClipboard(keysText)
        .then(() => {
            showNotification(`已成功复制 ${selectedKeys.length} 个选中的${type === 'valid' ? '有效' : '无效'}密钥`);
        })
        .catch((err) => {
            console.error('无法复制文本: ', err);
            showNotification('复制失败，请重试', 'error');
        });
}


// 单个复制保持不变
function copyKey(key) {
    copyToClipboard(key)
        .then(() => {
            showNotification(`已成功复制密钥`);
        })
        .catch((err) => {
            console.error('无法复制文本: ', err);
            showNotification('复制失败，请重试', 'error');
        });
}

// 移除 showCopyStatus 函数，因为它已被 showNotification 替代

async function verifyKey(key, button) {
    try {
        // 禁用按钮并显示加载状态
        button.disabled = true;
        const originalHtml = button.innerHTML;
        button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 验证中';

        try {
            const response = await fetch(`/gemini/v1beta/verify-key/${key}`, {
                method: 'POST'
            });
            const data = await response.json();

            // 根据验证结果更新UI并显示模态提示框
            if (data.success || data.status === 'valid') {
                // 验证成功，显示成功结果
                button.style.backgroundColor = '#27ae60';
                // 使用结果模态框显示成功消息
                showResultModal(true, '密钥验证成功');
                // 模态框关闭时会自动刷新页面
            } else {
                // 验证失败，显示失败结果
                const errorMsg = data.error || '密钥无效';
                button.style.backgroundColor = '#e74c3c';
                // 使用结果模态框显示失败消息，改为true以在关闭时刷新
                showResultModal(false, '密钥验证失败: ' + errorMsg, true);
            }
        } catch (fetchError) {
            console.error('API请求失败:', fetchError);
            showResultModal(false, '验证请求失败: ' + fetchError.message, true); // 改为true以在关闭时刷新
        } finally {
            // 1秒后恢复按钮原始状态 (如果页面不刷新)
            // 由于现在成功和失败都会刷新，这部分逻辑可以简化或移除
            // 但为了防止未来修改刷新逻辑，暂时保留，但可能不会执行
            setTimeout(() => {
                if (!document.getElementById('resultModal') || document.getElementById('resultModal').classList.contains('hidden')) {
                    button.innerHTML = originalHtml;
                    button.disabled = false;
                    button.style.backgroundColor = '';
                }
            }, 1000);
        }
    } catch (error) {
        console.error('验证失败:', error);
        // 确保在捕获到错误时恢复按钮状态 (如果页面不刷新)
        // button.disabled = false; // 由 finally 处理或因刷新而无需处理
        // button.innerHTML = '<i class="fas fa-check-circle"></i> 验证';
        showResultModal(false, '验证处理失败: ' + error.message, true); // 改为true以在关闭时刷新
    }
}


async function resetKeyFailCount(key, button) {
    try {
        // 禁用按钮并显示加载状态
        button.disabled = true;
        const originalHtml = button.innerHTML;
        button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 重置中';

        const response = await fetch(`/gemini/v1beta/reset-fail-count/${key}`, {
            method: 'POST'
        });
        const data = await response.json();

        // 根据重置结果更新UI
        if (data.success) {
            showNotification('失败计数重置成功');
            // 成功时保留绿色背景一会儿
            button.style.backgroundColor = '#27ae60';
            // 稍后刷新页面
            setTimeout(() => location.reload(), 1000);
        } else {
            const errorMsg = data.message || '重置失败';
            showNotification('重置失败: ' + errorMsg, 'error');
            // 失败时保留红色背景一会儿
            button.style.backgroundColor = '#e74c3c';
             // 如果失败，1秒后恢复按钮
             setTimeout(() => {
                 button.innerHTML = originalHtml;
                 button.disabled = false;
                 button.style.backgroundColor = '';
             }, 1000);
        }

        // 恢复按钮状态逻辑已移至成功/失败分支内

    } catch (error) {
        console.error('重置失败:', error);
        showNotification('重置请求失败: ' + error.message, 'error');
        // 确保在捕获到错误时恢复按钮状态
        button.disabled = false;
        button.innerHTML = '<i class="fas fa-redo-alt"></i> 重置'; // 恢复原始图标和文本
        button.style.backgroundColor = ''; // 清除可能设置的背景色
    }
}


// 显示重置确认模态框 (基于选中的密钥)
function showResetModal(type) {
    const modalElement = document.getElementById('resetModal');
    const titleElement = document.getElementById('resetModalTitle');
    const messageElement = document.getElementById('resetModalMessage');
    const confirmButton = document.getElementById('confirmResetBtn');

    const selectedKeys = getSelectedKeys(type);
    const count = selectedKeys.length;

    // 设置标题和消息
    titleElement.textContent = '批量重置失败次数';
    if (count > 0) {
        messageElement.textContent = `确定要批量重置选中的 ${count} 个${type === 'valid' ? '有效' : '无效'}密钥的失败次数吗？`;
        confirmButton.disabled = false; // 确保按钮可用
    } else {
        // 这个情况理论上不会发生，因为按钮在未选中时是禁用的
        messageElement.textContent = `请先选择要重置的${type === 'valid' ? '有效' : '无效'}密钥。`;
        confirmButton.disabled = true;
    }

    // 设置确认按钮事件
    confirmButton.onclick = () => executeResetAll(type);

    // 显示模态框
    modalElement.classList.remove('hidden');
}

function closeResetModal() {
    document.getElementById('resetModal').classList.add('hidden');
}

// 触发显示模态框
function resetAllKeysFailCount(type, event) {
    // 阻止事件冒泡
    if (event) {
        event.stopPropagation();
    }

    // 显示模态确认框
    showResetModal(type);
}

// 关闭模态框并根据参数决定是否刷新页面
function closeResultModal(reload = true) {
    document.getElementById('resultModal').classList.add('hidden');
    if (reload) {
        location.reload(); // 操作完成后刷新页面
    }
}

// 显示操作结果模态框 (通用版本)
function showResultModal(success, message, autoReload = true) {
    const modalElement = document.getElementById('resultModal');
    const titleElement = document.getElementById('resultModalTitle');
    const messageElement = document.getElementById('resultModalMessage');
    const iconElement = document.getElementById('resultIcon');
    const confirmButton = document.getElementById('resultModalConfirmBtn');

    // 设置标题
    titleElement.textContent = success ? '操作成功' : '操作失败';

    // 设置图标
    if (success) {
        iconElement.innerHTML = '<i class="fas fa-check-circle text-success-500"></i>';
        iconElement.className = 'text-6xl mb-3 text-success-500'; // 稍微增大图标
    } else {
        iconElement.innerHTML = '<i class="fas fa-times-circle text-danger-500"></i>';
        iconElement.className = 'text-6xl mb-3 text-danger-500'; // 稍微增大图标
    }

    // 清空现有内容并设置新消息
    messageElement.innerHTML = ''; // 清空
    if (typeof message === 'string') {
        // 对于普通字符串消息，保持原有逻辑
        const messageDiv = document.createElement('div');
        messageDiv.innerText = message; // 使用 innerText 防止 XSS
        messageElement.appendChild(messageDiv);
    } else if (message instanceof Node) {
        // 如果传入的是 DOM 节点，直接添加
        messageElement.appendChild(message);
    } else {
        // 其他类型转为字符串
        const messageDiv = document.createElement('div');
        messageDiv.innerText = String(message);
        messageElement.appendChild(messageDiv);
    }

    // 设置确认按钮点击事件
    confirmButton.onclick = () => closeResultModal(autoReload);

    // 显示模态框
    modalElement.classList.remove('hidden');
}

// 显示批量验证结果的专用模态框
function showVerificationResultModal(data) {
    const modalElement = document.getElementById('resultModal');
    const titleElement = document.getElementById('resultModalTitle');
    const messageElement = document.getElementById('resultModalMessage');
    const iconElement = document.getElementById('resultIcon');
    const confirmButton = document.getElementById('resultModalConfirmBtn');

    const successfulKeys = data.successful_keys || [];
    const failedKeys = data.failed_keys || {};
    const validCount = data.valid_count || 0;
    const invalidCount = data.invalid_count || 0;

    // 设置标题和图标
    titleElement.textContent = '批量验证结果';
    if (invalidCount === 0 && validCount > 0) {
        iconElement.innerHTML = '<i class="fas fa-check-double text-success-500"></i>';
        iconElement.className = 'text-6xl mb-3 text-success-500';
    } else if (invalidCount > 0 && validCount > 0) {
        iconElement.innerHTML = '<i class="fas fa-exclamation-triangle text-warning-500"></i>';
        iconElement.className = 'text-6xl mb-3 text-warning-500';
    } else if (invalidCount > 0 && validCount === 0) {
        iconElement.innerHTML = '<i class="fas fa-times-circle text-danger-500"></i>';
        iconElement.className = 'text-6xl mb-3 text-danger-500';
    } else { // 都为 0 或其他情况
        iconElement.innerHTML = '<i class="fas fa-info-circle text-gray-500"></i>';
        iconElement.className = 'text-6xl mb-3 text-gray-500';
    }

    // 构建详细内容
    messageElement.innerHTML = ''; // 清空

    const summaryDiv = document.createElement('div');
    summaryDiv.className = 'text-center mb-4 text-lg';
    summaryDiv.innerHTML = `验证完成：<span class="font-semibold text-success-600">${validCount}</span> 个成功，<span class="font-semibold text-danger-600">${invalidCount}</span> 个失败。`;
    messageElement.appendChild(summaryDiv);

    // 成功列表
    if (successfulKeys.length > 0) {
        const successDiv = document.createElement('div');
        successDiv.className = 'mb-3';
        const successHeader = document.createElement('div');
        successHeader.className = 'flex justify-between items-center mb-1';
        successHeader.innerHTML = `<h4 class="font-semibold text-success-700">成功密钥 (${successfulKeys.length}):</h4>`;

        const copySuccessBtn = document.createElement('button');
        copySuccessBtn.className = 'px-2 py-0.5 bg-green-100 hover:bg-green-200 text-green-700 text-xs rounded transition-colors';
        copySuccessBtn.innerHTML = '<i class="fas fa-copy mr-1"></i>复制全部';
        copySuccessBtn.onclick = (e) => {
            e.stopPropagation();
            copyToClipboard(successfulKeys.join('\n'))
                .then(() => showNotification(`已复制 ${successfulKeys.length} 个成功密钥`, 'success'))
                .catch(() => showNotification('复制失败', 'error'));
        };
        successHeader.appendChild(copySuccessBtn);
        successDiv.appendChild(successHeader);

        const successList = document.createElement('ul');
        successList.className = 'list-disc list-inside text-sm text-gray-600 max-h-20 overflow-y-auto bg-gray-50 p-2 rounded border border-gray-200';
        successfulKeys.forEach(key => {
            const li = document.createElement('li');
            li.className = 'font-mono';
            // Store full key in dataset for potential future use, display masked
            li.dataset.fullKey = key;
            li.textContent = key.substring(0, 4) + '...' + key.substring(key.length - 4);
            successList.appendChild(li);
        });
        successDiv.appendChild(successList);
        messageElement.appendChild(successDiv);
    }

    // 失败列表
    if (Object.keys(failedKeys).length > 0) {
        const failDiv = document.createElement('div');
        failDiv.className = 'mb-1'; // 减少底部边距
        const failHeader = document.createElement('div');
        failHeader.className = 'flex justify-between items-center mb-1';
        failHeader.innerHTML = `<h4 class="font-semibold text-danger-700">失败密钥 (${Object.keys(failedKeys).length}):</h4>`;

        const copyFailBtn = document.createElement('button');
        copyFailBtn.className = 'px-2 py-0.5 bg-red-100 hover:bg-red-200 text-red-700 text-xs rounded transition-colors';
        copyFailBtn.innerHTML = '<i class="fas fa-copy mr-1"></i>复制全部';
        const failedKeysArray = Object.keys(failedKeys); // Get array of failed keys
        copyFailBtn.onclick = (e) => {
            e.stopPropagation();
            copyToClipboard(failedKeysArray.join('\n'))
                .then(() => showNotification(`已复制 ${failedKeysArray.length} 个失败密钥`, 'success'))
                .catch(() => showNotification('复制失败', 'error'));
        };
        failHeader.appendChild(copyFailBtn);
        failDiv.appendChild(failHeader);

        const failList = document.createElement('ul');
        failList.className = 'text-sm text-gray-600 max-h-32 overflow-y-auto bg-red-50 p-2 rounded border border-red-200 space-y-1'; // 增加最大高度和间距
        Object.entries(failedKeys).forEach(([key, error]) => {
            const li = document.createElement('li');
            // li.className = 'flex justify-between items-center'; // Restore original layout
            li.className = 'flex flex-col items-start'; // Start with vertical layout

            const keySpanContainer = document.createElement('div');
            keySpanContainer.className = 'flex justify-between items-center w-full'; // Ensure key and button are on the same line initially

            const keySpan = document.createElement('span');
            keySpan.className = 'font-mono';
             // Store full key in dataset, display masked
            keySpan.dataset.fullKey = key;
            keySpan.textContent = key.substring(0, 4) + '...' + key.substring(key.length - 4);

            const detailsButton = document.createElement('button');
            detailsButton.className = 'ml-2 px-2 py-0.5 bg-red-200 hover:bg-red-300 text-red-700 text-xs rounded transition-colors';
            detailsButton.innerHTML = '<i class="fas fa-info-circle mr-1"></i>详情';
            detailsButton.dataset.error = error; // 将错误信息存储在 data 属性中
            detailsButton.onclick = (e) => {
                e.stopPropagation(); // Prevent modal close
                const button = e.currentTarget;
                const listItem = button.closest('li');
                const errorMsg = button.dataset.error;
                const errorDetailsId = `error-details-${key.replace(/[^a-zA-Z0-9]/g, '')}`; // Create unique ID
                let errorDiv = listItem.querySelector(`#${errorDetailsId}`);

                if (errorDiv) {
                    // Collapse: Remove error div and reset li layout
                    errorDiv.remove();
                    // listItem.className = 'flex justify-between items-center'; // Restore original layout
                    listItem.className = 'flex flex-col items-start'; // Keep vertical layout
                    button.innerHTML = '<i class="fas fa-info-circle mr-1"></i>详情'; // Restore button text
                } else {
                    // Expand: Create and append error div, change li layout
                    errorDiv = document.createElement('div');
                    errorDiv.id = errorDetailsId;
                    errorDiv.className = 'w-full mt-1 pl-0 text-xs text-red-600 bg-red-50 p-1 rounded border border-red-100 whitespace-pre-wrap break-words'; // Adjusted padding
                    errorDiv.textContent = errorMsg;
                    listItem.appendChild(errorDiv);
                    listItem.className = 'flex flex-col items-start'; // Change layout to vertical
                    button.innerHTML = '<i class="fas fa-chevron-up mr-1"></i>收起'; // Change button text
                    // Move button to be alongside the keySpan for vertical layout (already done)
                }
            };

            keySpanContainer.appendChild(keySpan); // Add keySpan to container
            keySpanContainer.appendChild(detailsButton); // Add button to container
            li.appendChild(keySpanContainer); // Add container to list item
            failList.appendChild(li);
        });
        failDiv.appendChild(failList);
        messageElement.appendChild(failDiv);
    }

    // 设置确认按钮点击事件 - 总是自动刷新
    confirmButton.onclick = () => closeResultModal(true); // Always reload

    // 显示模态框
    modalElement.classList.remove('hidden');
}


async function executeResetAll(type) {
    try {
        // 关闭确认模态框
        closeResetModal();

        // 找到对应的重置按钮以显示加载状态
        const resetButton = document.querySelector(`button[data-reset-type="${type}"]`);
        if (!resetButton) {
            showResultModal(false, `找不到${type === 'valid' ? '有效' : '无效'}密钥区域的批量重置按钮`, false); // Don't reload if button not found
            return;
        }

        // 获取选中的密钥
        const keysToReset = getSelectedKeys(type);

        if (keysToReset.length === 0) {
            showNotification(`没有选中的${type === 'valid' ? '有效' : '无效'}密钥可重置`, 'warning');
            return;
        }

        // 禁用按钮并显示加载状态
        resetButton.disabled = true;
        const originalHtml = resetButton.innerHTML;
        resetButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 重置中';

        try {
            // 调用新的后端 API 来重置选定的密钥
            const response = await fetch(`/gemini/v1beta/reset-selected-fail-counts`, { // 假设的新 API 端点
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ keys: keysToReset, key_type: type }) // 发送密钥列表和类型
            });

            if (!response.ok) {
                 // 尝试解析错误信息
                 let errorMsg = `服务器返回错误: ${response.status}`;
                 try {
                     const errorData = await response.json();
                     errorMsg = errorData.message || errorMsg;
                 } catch (e) {
                     // 如果解析失败，使用原始错误信息
                 }

                 throw new Error(errorMsg);
            }

            const data = await response.json();

            // 根据重置结果显示模态框
            if (data.success) {
                const message = data.reset_count !== undefined ?
                    `成功重置 ${data.reset_count} 个选中的${type === 'valid' ? '有效' : '无效'}密钥的失败次数` :
                    `成功重置 ${keysToReset.length} 个选中的密钥`;
                showResultModal(true, message); // 成功后刷新页面
            } else {
                const errorMsg = data.message || '批量重置失败';
                // 失败后不自动刷新页面，让用户看到错误信息
                showResultModal(false, '批量重置失败: ' + errorMsg, false);
            }
        } catch (fetchError) {
            console.error('API请求失败:', fetchError);
            showResultModal(false, '批量重置请求失败: ' + fetchError.message, false); // 失败后不自动刷新
        } finally {
            // 恢复按钮状态 (仅在不刷新的情况下)
             if (!document.getElementById('resultModal') || document.getElementById('resultModal').classList.contains('hidden') || document.getElementById('resultModalTitle').textContent.includes('失败')) {
                 resetButton.innerHTML = originalHtml;
                 resetButton.disabled = false;
             }
        }
    } catch (error) {
        console.error('批量重置处理失败:', error);
        showResultModal(false, '批量重置处理失败: ' + error.message, false); // 失败后不自动刷新
    }
}


function scrollToTop() {
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function scrollToBottom() {
    window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
}

// 移除这个函数，因为它可能正在干扰按钮的显示
// HTML中已经设置了滚动按钮为flex显示，不需要JavaScript额外控制
// function updateScrollButtons() {
//     // 不执行任何操作
// }

function refreshPage(button) {
    button.classList.add('loading'); // Maybe add a loading class for visual feedback
    button.disabled = true;
    const icon = button.querySelector('i');
    if (icon) icon.classList.add('fa-spin'); // Add spin animation

    setTimeout(() => {
        window.location.reload();
        // No need to remove loading/spin as page reloads
    }, 300);
}


// 恢复之前的 toggleSection 函数以修复展开/收缩动画
function toggleSection(header, sectionId) {
    const toggleIcon = header.querySelector('.toggle-icon');
    // 需要找到正确的 content 元素。它不再是紧邻的兄弟元素，而是 card 内的 key-content div
    const card = header.closest('.stats-card');
    const content = card ? card.querySelector('.key-content') : null;
    const batchActions = card ? card.querySelector('[id$="BatchActions"]') : null; // 获取批量操作栏
    const pagination = card ? card.querySelector('[id$="PaginationControls"]') : null; // 获取分页控件

    if (toggleIcon && content) {
        const isCollapsed = content.classList.contains('collapsed');

        // 切换图标状态
        toggleIcon.classList.toggle('collapsed', !isCollapsed);

        if (isCollapsed) {
            // 展开内容
            content.classList.remove('collapsed');
            // 先移除内联样式，让 CSS 控制初始状态
            content.style.maxHeight = '';
            content.style.opacity = '';
            content.style.padding = '';
            content.style.overflow = '';
            // 使用 requestAnimationFrame 确保浏览器应用了初始状态
            requestAnimationFrame(() => {
                // 计算内容的实际高度
                const scrollHeight = content.scrollHeight;
                let totalHeight = scrollHeight;

                 // 如果批量操作栏存在且可见，也计算其高度
                 if (batchActions && !batchActions.classList.contains('hidden')) {
                     totalHeight += batchActions.offsetHeight;
                 }
                 // 如果分页控件存在且可见，也计算其高度和 margin-top
                 if (pagination && pagination.offsetHeight > 0) {
                     // Assuming mt-4 which is 1rem = 16px (adjust if needed)
                     totalHeight += pagination.offsetHeight + 16;
                 }

                content.style.maxHeight = totalHeight + 'px';
                content.style.opacity = '1';
                content.style.padding = '1rem'; // 恢复 padding
                content.style.overflow = 'hidden'; // Keep hidden during transition

                // 动画结束后移除 max-height 以允许内容动态变化
                content.addEventListener('transitionend', function handler() {
                    content.removeEventListener('transitionend', handler);
                    if (!content.classList.contains('collapsed')) { // 确保是在展开状态
                       content.style.maxHeight = '';
                       content.style.overflow = 'visible';
                    }
                }, { once: true });
            });
        } else {
            // 收起内容
            // 先计算当前总高度
            let currentHeight = content.scrollHeight;
             if (batchActions && !batchActions.classList.contains('hidden')) {
                 currentHeight += batchActions.offsetHeight;
             }
             if (pagination && pagination.offsetHeight > 0) {
                 currentHeight += pagination.offsetHeight + 16;
             }
            // 设置一个明确的高度，然后过渡到 0
            content.style.maxHeight = currentHeight + 'px';
            content.style.overflow = 'hidden'; // Ensure overflow is hidden before starting transition
            requestAnimationFrame(() => {
                content.style.maxHeight = '0px';
                content.style.opacity = '0';
                content.style.padding = '0 1rem'; // 保持左右 padding，收起上下 padding
                content.classList.add('collapsed');
            });
        }
    } else {
        console.error("Toggle section failed: Icon or content not found.", header, sectionId);
    }
}


// 筛选有效密钥（根据失败次数阈值）并更新批量操作状态
function filterValidKeys() {
    const thresholdInput = document.getElementById('failCountThreshold');
    const validKeysList = document.getElementById('validKeys'); // Get the UL element
    if (!validKeysList) return; // Exit if the list doesn't exist

    const validKeyItems = validKeysList.querySelectorAll('li[data-key]'); // Select li elements within the list
    // 读取阈值，如果输入无效或为空，则默认为0（不过滤）
    const threshold = parseInt(thresholdInput.value, 10);
    const filterThreshold = isNaN(threshold) || threshold < 0 ? 0 : threshold;
    let hasVisibleItems = false;

    validKeyItems.forEach(item => {
        // 确保只处理包含 data-fail-count 的 li 元素
        if (item.dataset.failCount !== undefined) {
            const failCount = parseInt(item.dataset.failCount, 10);
            // 如果失败次数大于等于阈值，则显示，否则隐藏
            if (failCount >= filterThreshold) {
                item.style.display = 'flex'; // 使用 flex 因为 li 现在是 flex 容器
                hasVisibleItems = true;
            } else {
                item.style.display = 'none'; // 隐藏
                // 如果隐藏了一个项，取消其选中状态
                const checkbox = item.querySelector('.key-checkbox');
                if (checkbox && checkbox.checked) {
                    checkbox.checked = false;
                }
            }
        }
    });

    // 更新有效密钥的批量操作状态和全选复选框
    updateBatchActions('valid');

    // 处理“暂无有效密钥”消息
    const noMatchMsgId = 'no-valid-keys-msg';
    let noMatchMsg = validKeysList.querySelector(`#${noMatchMsgId}`);
    const initialKeyCount = validKeysList.querySelectorAll('li[data-key]').length; // 获取初始密钥数量

    if (!hasVisibleItems && initialKeyCount > 0) { // 仅当初始有密钥但现在都不可见时显示
        if (!noMatchMsg) {
            noMatchMsg = document.createElement('li');
            noMatchMsg.id = noMatchMsgId;
            noMatchMsg.className = 'text-center text-gray-500 py-4 col-span-full';
            noMatchMsg.textContent = '没有符合条件的有效密钥';
            validKeysList.appendChild(noMatchMsg);
        }
        noMatchMsg.style.display = '';
    } else if (noMatchMsg) {
        noMatchMsg.style.display = 'none';
    }
}


// 初始化
document.addEventListener('DOMContentLoaded', () => {
    // 初始化统计区块动画
    initStatItemAnimations();

    // 添加数字滚动动画效果
    const animateCounters = () => {
        const statValues = document.querySelectorAll('.stat-value');
        statValues.forEach(valueElement => {
            const finalValue = parseInt(valueElement.textContent, 10);
            if (!isNaN(finalValue)) {
                // 保存原始值以便稍后恢复
                if (!valueElement.dataset.originalValue) {
                    valueElement.dataset.originalValue = valueElement.textContent;
                }

                // 数字滚动动画
                let startValue = 0;
                const duration = 1500;
                const startTime = performance.now();

                const updateCounter = (currentTime) => {
                    const elapsedTime = currentTime - startTime;
                    if (elapsedTime < duration) {
                        const progress = elapsedTime / duration;
                        // 使用缓动函数使动画更自然
                        const easeOutValue = 1 - Math.pow(1 - progress, 3);
                        const currentValue = Math.floor(easeOutValue * finalValue);
                        valueElement.textContent = currentValue;
                        requestAnimationFrame(updateCounter);
                    } else {
                        // 恢复为原始值，以确保准确性
                        valueElement.textContent = valueElement.dataset.originalValue;
                    }


                };
                requestAnimationFrame(updateCounter);
            }
        });
    };

    // 在页面加载后启动数字动画
    setTimeout(animateCounters, 300);

    // 添加卡片悬停效果
    document.querySelectorAll('.stats-card').forEach(card => {
        card.addEventListener('mouseenter', () => {
            card.classList.add('shadow-lg');
            card.style.transform = 'translateY(-2px)';
        });

        card.addEventListener('mouseleave', () => {
            card.classList.remove('shadow-lg');
            card.style.transform = '';
        });
    });

    // 监听展开/折叠事件 (确保使用正确的选择器和函数)
    document.querySelectorAll('.stats-card-header').forEach(header => {
         // 检查 header 是否包含 toggle-icon，避免为其他卡片（如统计卡片）添加监听器
         if (header.querySelector('.toggle-icon')) {
             header.addEventListener('click', (event) => {
                 // 确保点击的不是内部交互元素（如输入框、复选框、标签、按钮、选择框）
                 if (event.target.closest('input, label, button, select')) {
                     return;
                 }
                 // 从 header 中提取 sectionId (例如从关联的 content div 的 id)
                 const card = header.closest('.stats-card');
                 const content = card ? card.querySelector('.key-content') : null;
                 const sectionId = content ? content.id : null;
                 if (sectionId) {
                    toggleSection(header, sectionId);
                 } else {
                     console.warn("Could not determine sectionId for toggle.");
                 }
             });
         }
    });

    // 添加筛选输入框事件监听
    const thresholdInput = document.getElementById('failCountThreshold');
    if (thresholdInput) {
        // 使用 'input' 事件实时响应输入变化
        thresholdInput.addEventListener('input', filterValidKeys);
        // 初始加载时应用一次筛选 (现在由 pagination/search 初始化处理)
        // filterValidKeys();
    }

    // --- 批量验证相关函数 (明确挂载到 window) ---

    // 显示验证确认模态框 (基于选中的密钥)
    window.showVerifyModal = function(type, event) {
        // 阻止事件冒泡（如果从按钮点击触发）
        if (event) {
            event.stopPropagation();
        }

        const modalElement = document.getElementById('verifyModal');
        const titleElement = document.getElementById('verifyModalTitle');
        const messageElement = document.getElementById('verifyModalMessage');
        const confirmButton = document.getElementById('confirmVerifyBtn');

        const selectedKeys = getSelectedKeys(type);
        const count = selectedKeys.length;

        // 设置标题和消息
        titleElement.textContent = '批量验证密钥';
        if (count > 0) {
            messageElement.textContent = `确定要批量验证选中的 ${count} 个${type === 'valid' ? '有效' : '无效'}密钥吗？此操作可能需要一些时间。`;
            confirmButton.disabled = false; // 确保按钮可用
        } else {
            // 这个情况理论上不会发生，因为按钮在未选中时是禁用的
            messageElement.textContent = `请先选择要验证的${type === 'valid' ? '有效' : '无效'}密钥。`;
            confirmButton.disabled = true;
        }

        // 设置确认按钮事件
        confirmButton.onclick = () => executeVerifyAll(type);

        // 显示模态框
        modalElement.classList.remove('hidden');
    }

    window.closeVerifyModal = function() {
        document.getElementById('verifyModal').classList.add('hidden');
    }

    window.executeVerifyAll = async function(type) {
        try {
            // 关闭确认模态框
            closeVerifyModal();

            // 找到对应的验证按钮以显示加载状态
            const verifyButton = document.querySelector(`#${type}BatchActions button:nth-child(1)`); // Assuming verify is the first button
            let originalVerifyHtml = '';
            if (verifyButton) {
                originalVerifyHtml = verifyButton.innerHTML;
                verifyButton.disabled = true;
                verifyButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 验证中';
            }


            // 获取选中的密钥
            const keysToVerify = getSelectedKeys(type);

            if (keysToVerify.length === 0) {
                showNotification(`没有选中的${type === 'valid' ? '有效' : '无效'}密钥可验证`, 'warning');
                 if (verifyButton) { // Restore button if no keys selected
                     verifyButton.innerHTML = originalVerifyHtml;
                     // Button disable state will be handled by updateBatchActions after reload or modal close
                 }
                return;
            }

            // 显示一个通用的加载提示
            showNotification('开始批量验证，请稍候...', 'info');

            // 调用新的后端 API 来验证选定的密钥
            const response = await fetch(`/gemini/v1beta/verify-selected-keys`, { // 假设的新 API 端点
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ keys: keysToVerify }) // 只发送密钥列表
            });

            if (!response.ok) {
                 let errorMsg = `服务器返回错误: ${response.status}`;
                 try {
                     const errorData = await response.json();
                     errorMsg = errorData.message || errorMsg;
                 } catch (e) { /*忽略解析错误*/ }
                 throw new Error(errorMsg);
            }

            const data = await response.json();

            // 使用新的专用模态框显示结果
            showVerificationResultModal(data);
            // 注意：autoReload 逻辑已移至 showVerificationResultModal 内部 (现在总是刷新)

        } catch (error) {
            console.error('批量验证处理失败:', error);
            // 失败后也刷新页面，让用户看到可能更新的状态
            showResultModal(false, '批量验证处理失败: ' + error.message, true);
        } finally {
             // 可以在这里移除加载指示器
             console.log("Bulk verification process finished.");
             // Button state will be reset on page reload
        }
    }

    // --- 复选框事件监听 ---
    // Attach listeners dynamically after pagination renders content, or use event delegation
    document.getElementById('validKeys').addEventListener('change', (event) => {
        if (event.target.classList.contains('key-checkbox')) {
            updateBatchActions('valid');
        }
    });
    document.getElementById('invalidKeys').addEventListener('change', (event) => {
        if (event.target.classList.contains('key-checkbox')) {
            updateBatchActions('invalid');
        }
    });


    // 初始化批量操作区域状态 (在 pagination 初始化后进行)
    // updateBatchActions('valid'); // Called by displayPage
    // updateBatchActions('invalid'); // Called by displayPage


    // --- 滚动和页面控制 --- (Scroll buttons handled by base.html)
    // --- 自动刷新控制 ---
    const autoRefreshToggle = document.getElementById('autoRefreshToggle');
    const autoRefreshIntervalTime = 60000; // 60秒
    let autoRefreshTimer = null;

    function startAutoRefresh() {
        if (autoRefreshTimer) return; // 防止重复启动
        console.log('启动自动刷新...');
        showNotification('自动刷新已启动', 'info', 2000);
        autoRefreshTimer = setInterval(() => {
            console.log('自动刷新 keys_status 页面...');
            location.reload();
        }, autoRefreshIntervalTime);
    }

    function stopAutoRefresh() {
        if (autoRefreshTimer) {
            console.log('停止自动刷新...');
            showNotification('自动刷新已停止', 'info', 2000);
            clearInterval(autoRefreshTimer);
            autoRefreshTimer = null;
        }
    }

    if (autoRefreshToggle) {
        // 从 localStorage 读取状态并初始化
        const isAutoRefreshEnabled = localStorage.getItem('autoRefreshEnabled') === 'true';
        autoRefreshToggle.checked = isAutoRefreshEnabled;
        if (isAutoRefreshEnabled) {
            startAutoRefresh();
        }

        // 添加事件监听器
        autoRefreshToggle.addEventListener('change', () => {
            if (autoRefreshToggle.checked) {
                localStorage.setItem('autoRefreshEnabled', 'true');
                startAutoRefresh();
            } else {
                localStorage.setItem('autoRefreshEnabled', 'false');
                stopAutoRefresh();
            }
        });
    }

    // --- Pagination and Search Initialization ---
    // This part needs to be integrated with the pagination logic from the provided file content
    // Assuming the pagination/search related code from the file_content is now part of this script

    // --- Get DOM Elements for Pagination/Search ---
    const validKeysListElement = document.getElementById('validKeys');
    const invalidKeysListElement = document.getElementById('invalidKeys');
    // const thresholdInput = document.getElementById('failCountThreshold'); // Already defined
    const searchInput = document.getElementById('keySearchInput');
    const itemsPerPageSelect = document.getElementById('itemsPerPageSelect');

    // --- Store Initial Key Data ---
    if (validKeysListElement) {
        allValidKeys = Array.from(validKeysListElement.querySelectorAll('li[data-key]'));
        allValidKeys.forEach(li => {
            const keyTextSpan = li.querySelector('.key-text');
            if (keyTextSpan && keyTextSpan.dataset.fullKey) {
                li.dataset.key = keyTextSpan.dataset.fullKey; // Ensure li has full key for search
            }
        });
        filteredValidKeys = [...allValidKeys]; // Start with all keys
    }
    if (invalidKeysListElement) {
        allInvalidKeys = Array.from(invalidKeysListElement.querySelectorAll('li[data-key]'));
         allInvalidKeys.forEach(li => {
            const keyTextSpan = li.querySelector('.key-text');
            if (keyTextSpan && keyTextSpan.dataset.fullKey) {
                li.dataset.key = keyTextSpan.dataset.fullKey;
            }
        });
    }

    // --- Initial Display ---
    if (itemsPerPageSelect) {
        itemsPerPage = parseInt(itemsPerPageSelect.value, 10);
    }
    filterAndSearchValidKeys(); // This applies initial filter/search and calls displayPage('valid', 1, ...)
    displayPage('invalid', 1, allInvalidKeys); // Display first page of invalid keys

    // --- Event Listeners for Pagination/Search ---
    if (thresholdInput) {
        thresholdInput.addEventListener('input', filterAndSearchValidKeys);
    }
    if (searchInput) {
        searchInput.addEventListener('input', filterAndSearchValidKeys);
    }
    if (itemsPerPageSelect) {
        itemsPerPageSelect.addEventListener('change', () => {
            itemsPerPage = parseInt(itemsPerPageSelect.value, 10);
            filterAndSearchValidKeys(); // Re-filter and display page 1
        });
    }

});

// Service Worker registration
if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        navigator.serviceWorker.register('/static/service-worker.js')
            .then(registration => {
                console.log('ServiceWorker注册成功:', registration.scope);
            })
            .catch(error => {
                console.log('ServiceWorker注册失败:', error);
            });
    });
}
function toggleKeyVisibility(button) {
    const keyContainer = button.closest('.flex.items-center.gap-1');
    const keyTextSpan = keyContainer.querySelector('.key-text');
    const eyeIcon = button.querySelector('i');
    const fullKey = keyTextSpan.dataset.fullKey;
    const maskedKey = fullKey.substring(0, 4) + '...' + fullKey.substring(fullKey.length - 4);

    if (keyTextSpan.textContent === maskedKey) {
        keyTextSpan.textContent = fullKey;
        eyeIcon.classList.remove('fa-eye');
        eyeIcon.classList.add('fa-eye-slash');
        button.title = '隐藏密钥';
    } else {
        keyTextSpan.textContent = maskedKey;
        eyeIcon.classList.remove('fa-eye-slash');
        eyeIcon.classList.add('fa-eye');
        button.title = '显示密钥';
    }
}

// --- API 调用详情模态框逻辑 ---

// 显示 API 调用详情模态框
async function showApiCallDetails(period) {
    const modal = document.getElementById('apiCallDetailsModal');
    const contentArea = document.getElementById('apiCallDetailsContent');
    const titleElement = document.getElementById('apiCallDetailsModalTitle');

    if (!modal || !contentArea || !titleElement) {
        console.error('无法找到 API 调用详情模态框元素');
        showNotification('无法显示详情，页面元素缺失', 'error');
        return;
    }

    // 设置标题
    let periodText = '';
    switch (period) {
        case '1m': periodText = '最近 1 分钟'; break;
        case '1h': periodText = '最近 1 小时'; break;
        case '24h': periodText = '最近 24 小时'; break;
        default: periodText = '指定时间段';
    }
    titleElement.textContent = `${periodText} API 调用详情`;

    // 显示模态框并设置加载状态
    modal.classList.remove('hidden');
    contentArea.innerHTML = `
        <div class="text-center py-10">
             <i class="fas fa-spinner fa-spin text-primary-600 text-3xl"></i>
             <p class="text-gray-500 mt-2">加载中...</p>
        </div>`;

    try {
        // 调用后端 API 获取数据
        const response = await fetch(`/api/stats/details?period=${period}`);
        if (!response.ok) {
            let errorMsg = `服务器错误: ${response.status}`;
             try {
                 const errorData = await response.json();
                 errorMsg = errorData.detail || errorMsg;
             } catch (e) { /* 忽略解析错误 */ }
            throw new Error(errorMsg);
        }
        const data = await response.json();

        // 渲染数据
        renderApiCallDetails(data, contentArea);

    } catch (error) {
        console.error('获取 API 调用详情失败:', error);
        contentArea.innerHTML = `
            <div class="text-center py-10 text-danger-500">
                <i class="fas fa-exclamation-triangle text-3xl"></i>
                <p class="mt-2">加载失败: ${error.message}</p>
            </div>`;
    }
}

// 关闭 API 调用详情模态框
function closeApiCallDetailsModal() {
    const modal = document.getElementById('apiCallDetailsModal');
    if (modal) {
        modal.classList.add('hidden');
    }
}

// 渲染 API 调用详情到模态框
function renderApiCallDetails(data, container) {
    if (!data || data.length === 0) {
        container.innerHTML = `
            <div class="text-center py-10 text-gray-500">
                <i class="fas fa-info-circle text-3xl"></i>
                <p class="mt-2">该时间段内没有 API 调用记录。</p>
            </div>`;
        return;
    }

    // 创建表格
    let tableHtml = `
        <table class="min-w-full divide-y divide-gray-200">
            <thead class="bg-gray-50">
                <tr>
                    <th scope="col" class="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">时间</th>
                    <th scope="col" class="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">密钥 (部分)</th>
                    <th scope="col" class="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">模型</th>
                    <th scope="col" class="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">状态</th>
                </tr>
            </thead>
            <tbody class="bg-white divide-y divide-gray-200">
    `;

    // 填充表格行
    data.forEach(call => {
        const timestamp = new Date(call.timestamp).toLocaleString();
        const keyDisplay = call.key ? `${call.key.substring(0, 4)}...${call.key.substring(call.key.length - 4)}` : 'N/A';
        const statusClass = call.status === 'success' ? 'text-success-600' : 'text-danger-600';
        const statusIcon = call.status === 'success' ? 'fa-check-circle' : 'fa-times-circle';

        tableHtml += `
            <tr>
                <td class="px-4 py-2 whitespace-nowrap text-sm text-gray-700">${timestamp}</td>
                <td class="px-4 py-2 whitespace-nowrap text-sm text-gray-500 font-mono">${keyDisplay}</td>
                <td class="px-4 py-2 whitespace-nowrap text-sm text-gray-500">${call.model || 'N/A'}</td>
                <td class="px-4 py-2 whitespace-nowrap text-sm ${statusClass}">
                    <i class="fas ${statusIcon} mr-1"></i>
                    ${call.status}
                </td>
            </tr>
        `;
    });

    tableHtml += `
            </tbody>
        </table>
    `;

    container.innerHTML = tableHtml;
}

// --- 密钥使用详情模态框逻辑 ---

// 显示密钥使用详情模态框
window.showKeyUsageDetails = async function(key) {
    const modal = document.getElementById('keyUsageDetailsModal');
    const contentArea = document.getElementById('keyUsageDetailsContent');
    const titleElement = document.getElementById('keyUsageDetailsModalTitle');
    const keyDisplay = key.substring(0, 4) + '...' + key.substring(key.length - 4);

    if (!modal || !contentArea || !titleElement) {
        console.error('无法找到密钥使用详情模态框元素');
        showNotification('无法显示详情，页面元素缺失', 'error');
        return;
    }

    // 设置标题
    titleElement.textContent = `密钥 ${keyDisplay} - 最近24小时请求详情`;

    // 显示模态框并设置加载状态
    modal.classList.remove('hidden');
    contentArea.innerHTML = `
        <div class="text-center py-10">
             <i class="fas fa-spinner fa-spin text-primary-600 text-3xl"></i>
             <p class="text-gray-500 mt-2">加载中...</p>
        </div>`;

    try {
        // 调用新的后端 API 获取数据
        // 注意：后端需要实现 /api/key-usage-details/{key} 端点
        const response = await fetch(`/api/key-usage-details/${key}`);
        if (!response.ok) {
            let errorMsg = `服务器错误: ${response.status}`;
            try {
                const errorData = await response.json();
                errorMsg = errorData.detail || errorMsg; // 假设后端错误信息在 detail 字段
            } catch (e) { /* 忽略解析错误 */ }
            throw new Error(errorMsg);
        }
        const data = await response.json();

        // 渲染数据
        renderKeyUsageDetails(data, contentArea);

    } catch (error) {
        console.error('获取密钥使用详情失败:', error);
        contentArea.innerHTML = `
            <div class="text-center py-10 text-danger-500">
                <i class="fas fa-exclamation-triangle text-3xl"></i>
                <p class="mt-2">加载失败: ${error.message}</p>
            </div>`;
    }
}

// 关闭密钥使用详情模态框
window.closeKeyUsageDetailsModal = function() {
    const modal = document.getElementById('keyUsageDetailsModal');
    if (modal) {
        modal.classList.add('hidden');
    }
}

// 渲染密钥使用详情到模态框 (这个函数主要由 showKeyUsageDetails 调用，不一定需要全局，但保持一致性)
window.renderKeyUsageDetails = function(data, container) {
    // data 预期格式: { "model_name1": count1, "model_name2": count2, ... }
    if (!data || Object.keys(data).length === 0) {
        container.innerHTML = `
            <div class="text-center py-10 text-gray-500">
                <i class="fas fa-info-circle text-3xl"></i>
                <p class="mt-2">该密钥在最近24小时内没有调用记录。</p>
            </div>`;
        return;
    }

    // 创建表格
    let tableHtml = `
        <table class="min-w-full divide-y divide-gray-200">
            <thead class="bg-gray-50">
                <tr>
                    <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">模型名称</th>
                    <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">调用次数 (24h)</th>
                </tr>
            </thead>
            <tbody class="bg-white divide-y divide-gray-200">
    `;

    // 排序模型（可选，按调用次数降序）
    const sortedModels = Object.entries(data).sort(([, countA], [, countB]) => countB - countA);

    // 填充表格行
    sortedModels.forEach(([model, count]) => {
        tableHtml += `
            <tr>
                <td class="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">${model}</td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">${count}</td>
            </tr>
        `;
    });

    tableHtml += `
            </tbody>
        </table>
    `;

    container.innerHTML = tableHtml;
}

// --- Global Variables for Pagination ---
let itemsPerPage = 10; // Default, will be updated from select
let validCurrentPage = 1;
let invalidCurrentPage = 1;
let allValidKeys = []; // Stores all original valid key li elements
let allInvalidKeys = []; // Stores all original invalid key li elements
let filteredValidKeys = []; // Stores filtered and searched valid key li elements

// --- Key List Display & Pagination ---

/**
 * Displays key list items for a specific type and page.
 * @param {string} type 'valid' or 'invalid'
 * @param {number} page Page number (1-based)
 * @param {Array} keyItemsArray The array of li elements to paginate (e.g., filteredValidKeys, allInvalidKeys)
 */
function displayPage(type, page, keyItemsArray) {
    const listElement = document.getElementById(`${type}Keys`);
    const paginationControls = document.getElementById(`${type}PaginationControls`);
    if (!listElement || !paginationControls) return;

    // Update current page based on type
    if (type === 'valid') {
        validCurrentPage = page;
        // Read itemsPerPage from the select specifically for valid keys
        const itemsPerPageSelect = document.getElementById('itemsPerPageSelect');
        itemsPerPage = itemsPerPageSelect ? parseInt(itemsPerPageSelect.value, 10) : 10;
    } else {
        invalidCurrentPage = page;
        // For invalid keys, use a fixed itemsPerPage or the same global one
        // itemsPerPage = 10; // Or read from a different select if needed
    }

    const totalItems = keyItemsArray.length;
    const totalPages = Math.ceil(totalItems / itemsPerPage);
    page = Math.max(1, Math.min(page, totalPages || 1)); // Ensure page is valid

    // Update current page variable again after validation
    if (type === 'valid') {
        validCurrentPage = page;
    } else {
        invalidCurrentPage = page;
    }


    const startIndex = (page - 1) * itemsPerPage;
    const endIndex = startIndex + itemsPerPage;

    listElement.innerHTML = ''; // Clear current list content

    const pageItems = keyItemsArray.slice(startIndex, endIndex);

    if (pageItems.length > 0) {
        pageItems.forEach(item => listElement.appendChild(item.cloneNode(true))); // Clone node to avoid issues if original array is modified elsewhere
    } else if (totalItems === 0 && type === 'valid' && (document.getElementById('failCountThreshold').value !== '0' || document.getElementById('keySearchInput').value !== '')) {
        // Handle empty state after filtering/searching for valid keys
        const noMatchMsgId = 'no-valid-keys-msg';
        let noMatchMsg = listElement.querySelector(`#${noMatchMsgId}`);
        if (!noMatchMsg) {
            noMatchMsg = document.createElement('li');
            noMatchMsg.id = noMatchMsgId;
            noMatchMsg.className = 'text-center text-gray-500 py-4 col-span-full';
            noMatchMsg.textContent = '没有符合条件的有效密钥';
            listElement.appendChild(noMatchMsg);
        }
        noMatchMsg.style.display = '';
    } else if (totalItems === 0) {
        // Handle empty state for initially empty lists
        const emptyMsg = document.createElement('li');
        emptyMsg.className = 'text-center text-gray-500 py-4 col-span-full';
        emptyMsg.textContent = `暂无${type === 'valid' ? '有效' : '无效'}密钥`;
        listElement.appendChild(emptyMsg);
    }

    setupPaginationControls(type, page, totalPages, keyItemsArray);
    updateBatchActions(type); // Update batch actions based on the currently displayed page
    // Re-attach event listeners for buttons inside the newly added list items if needed (using event delegation is better)
}

/**
 * Sets up pagination controls.
 * @param {string} type 'valid' or 'invalid'
 * @param {number} currentPage Current page number
 * @param {number} totalPages Total number of pages
 * @param {Array} keyItemsArray The array of li elements being paginated
 */
function setupPaginationControls(type, currentPage, totalPages, keyItemsArray) {
    const controlsContainer = document.getElementById(`${type}PaginationControls`);
    if (!controlsContainer) return;

    controlsContainer.innerHTML = '';

    if (totalPages <= 1) {
        return; // No controls needed for single/no page
    }

    // Previous Button
    const prevButton = document.createElement('button');
    prevButton.innerHTML = '<i class="fas fa-chevron-left"></i>';
    prevButton.className = 'px-3 py-1 rounded bg-gray-200 hover:bg-gray-300 disabled:opacity-50 disabled:cursor-not-allowed text-sm';
    prevButton.disabled = currentPage === 1;
    prevButton.onclick = () => displayPage(type, currentPage - 1, keyItemsArray);
    controlsContainer.appendChild(prevButton);

    // Page Number Buttons (Logic for ellipsis)
    const maxPageButtons = 5;
    let startPage = Math.max(1, currentPage - Math.floor(maxPageButtons / 2));
    let endPage = Math.min(totalPages, startPage + maxPageButtons - 1);

    if (endPage - startPage + 1 < maxPageButtons) {
        startPage = Math.max(1, endPage - maxPageButtons + 1);
    }

    // First Page Button & Ellipsis
    if (startPage > 1) {
        const firstPageButton = document.createElement('button');
        firstPageButton.textContent = '1';
        firstPageButton.className = 'px-3 py-1 rounded bg-gray-200 hover:bg-gray-300 text-sm';
        firstPageButton.onclick = () => displayPage(type, 1, keyItemsArray);
        controlsContainer.appendChild(firstPageButton);
        if (startPage > 2) {
            const ellipsis = document.createElement('span');
            ellipsis.textContent = '...';
            ellipsis.className = 'px-3 py-1 text-gray-500 text-sm';
            controlsContainer.appendChild(ellipsis);
        }
    }

    // Middle Page Buttons
    for (let i = startPage; i <= endPage; i++) {
        const pageButton = document.createElement('button');
        pageButton.textContent = i;
        pageButton.className = `px-3 py-1 rounded text-sm ${i === currentPage ? 'bg-primary-600 text-white font-semibold' : 'bg-gray-200 hover:bg-gray-300'}`;
        pageButton.onclick = () => displayPage(type, i, keyItemsArray);
        controlsContainer.appendChild(pageButton);
    }

    // Ellipsis & Last Page Button
    if (endPage < totalPages) {
        if (endPage < totalPages - 1) {
            const ellipsis = document.createElement('span');
            ellipsis.textContent = '...';
            ellipsis.className = 'px-3 py-1 text-gray-500 text-sm';
            controlsContainer.appendChild(ellipsis);
        }
        const lastPageButton = document.createElement('button');
        lastPageButton.textContent = totalPages;
        lastPageButton.className = 'px-3 py-1 rounded bg-gray-200 hover:bg-gray-300 text-sm';
        lastPageButton.onclick = () => displayPage(type, totalPages, keyItemsArray);
        controlsContainer.appendChild(lastPageButton);
    }

    // Next Button
    const nextButton = document.createElement('button');
    nextButton.innerHTML = '<i class="fas fa-chevron-right"></i>';
    nextButton.className = 'px-3 py-1 rounded bg-gray-200 hover:bg-gray-300 disabled:opacity-50 disabled:cursor-not-allowed text-sm';
    nextButton.disabled = currentPage === totalPages;
    nextButton.onclick = () => displayPage(type, currentPage + 1, keyItemsArray);
    controlsContainer.appendChild(nextButton);
}


// --- Filtering & Searching (Valid Keys Only) ---

/**
 * Filters and searches the valid keys based on threshold and search term.
 * Updates the `filteredValidKeys` array and redisplays the first page.
 */
function filterAndSearchValidKeys() {
    const thresholdInput = document.getElementById('failCountThreshold');
    const searchInput = document.getElementById('keySearchInput');

    const threshold = parseInt(thresholdInput.value, 10);
    const filterThreshold = isNaN(threshold) || threshold < 0 ? 0 : threshold;
    const searchTerm = searchInput.value.trim().toLowerCase();

    // Filter from the original full list (allValidKeys)
    filteredValidKeys = allValidKeys.filter(item => {
        const failCount = parseInt(item.dataset.failCount, 10);
        const fullKey = item.dataset.key || ''; // Use data-key which should hold the full key

        const failCountMatch = failCount >= filterThreshold;
        const searchMatch = searchTerm === '' || fullKey.toLowerCase().includes(searchTerm);

        return failCountMatch && searchMatch;
    });

    // Reset to the first page after filtering/searching
    validCurrentPage = 1;
    displayPage('valid', validCurrentPage, filteredValidKeys);
}
