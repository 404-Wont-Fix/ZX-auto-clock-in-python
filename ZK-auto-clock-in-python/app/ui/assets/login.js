/**
 * 登录页面脚本
 */

async function handleLogin(e) {
    e.preventDefault();
    const btn = document.getElementById('loginBtn');
    btn.disabled = true;
    btn.textContent = '登录中...';

    try {
        const res = await fetch('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({
                username: document.getElementById('username').value,
                password: document.getElementById('password').value
            })
        });
        const data = await res.json();
        if (data.success) {
            // 保存 token 到 localStorage
            localStorage.setItem('auth_token', data.token);
            btn.textContent = '✓ 登录成功';
            await new Promise(r => setTimeout(r, 300));
            window.location.href = '/dashboard';
        } else {
            document.getElementById('errorMessage').textContent = data.error;
            document.getElementById('errorMessage').classList.add('show');
            btn.disabled = false;
            btn.textContent = '登录';
        }
    } catch (err) {
        document.getElementById('errorMessage').textContent = '网络错误，请稍后重试';
        document.getElementById('errorMessage').classList.add('show');
        btn.disabled = false;
        btn.textContent = '登录';
    }
}
