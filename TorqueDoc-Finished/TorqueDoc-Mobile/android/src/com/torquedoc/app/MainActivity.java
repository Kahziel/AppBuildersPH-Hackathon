package com.torquedoc.app;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.webkit.*;
import android.widget.LinearLayout;
import android.widget.Toast;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import org.json.JSONObject;

/** Serves the entire signed APK library from a private HTTPS origin, without a server. */
public final class MainActivity extends Activity {
    private static final String HOST = "appassets.androidplatform.net";
    private static final String HOME = "https://" + HOST + "/index.html";
    private static final int CHOOSE_LOG = 41, EXPORT_LOG = 42;
    private WebView web;
    private ValueCallback<Uri[]> fileCallback;
    private byte[] pendingExport;

    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        getWindow().setStatusBarColor(Color.rgb(12,14,17));
        getWindow().setNavigationBarColor(Color.rgb(12,14,17));
        LinearLayout root = new LinearLayout(this);
        root.setBackgroundColor(Color.rgb(12,14,17));
        root.setOnApplyWindowInsetsListener((view,insets) -> {
            view.setPadding(insets.getSystemWindowInsetLeft(), insets.getSystemWindowInsetTop(),
                insets.getSystemWindowInsetRight(), insets.getSystemWindowInsetBottom());
            return insets.consumeSystemWindowInsets();
        });
        web = new WebView(this);
        root.addView(web, new LinearLayout.LayoutParams(-1,-1));
        setContentView(root);
        web.setBackgroundColor(Color.rgb(12,14,17));
        WebSettings settings = web.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(true); // Android's user-selected JSON document URI only.
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setMediaPlaybackRequiresUserGesture(true);
        settings.setSupportMultipleWindows(false);
        web.setWebViewClient(new WebViewClient() {
            @Override public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                if (!HOST.equals(uri.getHost())) return null;
                if (!"https".equals(uri.getScheme()) || !"GET".equals(request.getMethod())) return missing();
                String path = uri.getPath();
                if (path == null || path.equals("/")) path = "/index.html";
                if (path.contains("..") || path.contains("\\") || path.indexOf('\0') >= 0) return missing();
                try {
                    InputStream input = getAssets().open("public" + path);
                    Map<String,String> headers = new HashMap<>();
                    headers.put("Cross-Origin-Opener-Policy", "same-origin");
                    headers.put("Cross-Origin-Embedder-Policy", "require-corp");
                    headers.put("Cross-Origin-Resource-Policy", "same-origin");
                    headers.put("X-Content-Type-Options", "nosniff");
                    return new WebResourceResponse(mime(path), "UTF-8", 200, "OK", headers, input);
                } catch (IOException e) { return missing(); }
            }
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                if ("https".equals(uri.getScheme()) && HOST.equals(uri.getHost())) return false;
                if (request.isForMainFrame() && ("https".equals(uri.getScheme()) || "http".equals(uri.getScheme()))) {
                    try { startActivity(new Intent(Intent.ACTION_VIEW, uri)); }
                    catch (ActivityNotFoundException e) { message("No browser is installed to open this link."); }
                }
                return true;
            }
            @Override public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) message("Unable to load the bundled app. Close and reopen TorqueDoc.");
            }
        });
        web.setWebChromeClient(new WebChromeClient() {
            @Override public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
                if (fileCallback != null) fileCallback.onReceiveValue(null);
                fileCallback = callback;
                Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
                intent.addCategory(Intent.CATEGORY_OPENABLE);
                intent.setType("*/*");
                intent.putExtra(Intent.EXTRA_MIME_TYPES, new String[]{"application/json", "text/plain"});
                try { startActivityForResult(intent, CHOOSE_LOG); }
                catch (ActivityNotFoundException e) { fileCallback.onReceiveValue(null); fileCallback=null;message("No file picker is installed."); }
                return true;
            }
            @Override public boolean onJsPrompt(WebView view, String url, String name, String value, JsPromptResult result) {
                Uri source = Uri.parse(url);
                if (!HOST.equals(source.getHost()) || !"https".equals(source.getScheme()) || !"TorqueDoc.export".equals(name)) return false;
                try {
                    if (pendingExport != null) throw new IllegalStateException("Another export is already open.");
                    JSONObject payload = new JSONObject(value);
                    String text = payload.getString("text");
                    if (text.length() > 10_000_000) throw new IllegalArgumentException("Export is too large.");
                    // Only JSON maintenance data is accepted. No paths or arbitrary native commands.
                    new JSONObject(text);
                    pendingExport = text.getBytes(StandardCharsets.UTF_8);
                    String filename = payload.optString("name", "torquedoc-maintenance.json").replaceAll("[^A-Za-z0-9._-]", "_");
                    if (!filename.endsWith(".json")) filename += ".json";
                    Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT);
                    intent.addCategory(Intent.CATEGORY_OPENABLE);
                    intent.setType("application/json");
                    intent.putExtra(Intent.EXTRA_TITLE, filename);
                    startActivityForResult(intent, EXPORT_LOG);
                    result.confirm("pending");
                } catch (Exception e) { pendingExport=null;result.confirm("error");message("Could not open export: " + e.getMessage()); }
                return true;
            }
        });
        web.loadUrl(HOME);
        if (android.os.Build.VERSION.SDK_INT >= 33) {
            getOnBackInvokedDispatcher().registerOnBackInvokedCallback(
                android.window.OnBackInvokedDispatcher.PRIORITY_DEFAULT, this::handleBack);
        }
    }

    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request,result,data);
        if (request == CHOOSE_LOG && fileCallback != null) {
            fileCallback.onReceiveValue(result == RESULT_OK && data != null && data.getData() != null ? new Uri[]{data.getData()} : null);
            fileCallback=null;
        }
        if (request == EXPORT_LOG) {
            String outcome="cancelled";
            if (result == RESULT_OK && data != null && pendingExport != null) {
                try (OutputStream out=getContentResolver().openOutputStream(data.getData(), "wt")) {
                    if (out == null) throw new IOException("No writable file selected.");
                    out.write(pendingExport);outcome="saved";
                } catch (Exception e) { outcome="error";message("Export failed: " + e.getMessage()); }
            }
            pendingExport=null;
            web.evaluateJavascript("window.dispatchEvent(new CustomEvent('torquedoc-export-result',{detail:" + JSONObject.quote(outcome) + "}));", null);
        }
    }

    @Override public void onBackPressed() {
        handleBack();
    }
    private void handleBack() {
        web.evaluateJavascript("(()=>{const close=document.querySelector('#modal-root [data-action=close-modal]');if(close){close.click();return true;}const nav=document.querySelector('.sidebar.open');if(nav){document.querySelector('[data-action=close-menu]')?.click();return true;}return false;})()", result -> {
            if ("true".equals(result)) return;
            if (web.canGoBack()) web.goBack(); else finish();
        });
    }
    @Override protected void onDestroy() {
        if (fileCallback != null) fileCallback.onReceiveValue(null);
        if (web != null) { web.stopLoading();web.destroy(); }
        super.onDestroy();
    }
    private void message(String text) { Toast.makeText(this,text,Toast.LENGTH_LONG).show(); }
    private static WebResourceResponse missing() {
        return new WebResourceResponse("text/plain", "UTF-8", 404,"Not Found",new HashMap<>(),new ByteArrayInputStream("Bundled file not found".getBytes(StandardCharsets.UTF_8)));
    }
    private static String mime(String path) {
        String p=path.toLowerCase(Locale.ROOT);
        if(p.endsWith(".html")) return "text/html";
        if(p.endsWith(".js") || p.endsWith(".mjs")) return "text/javascript";
        if(p.endsWith(".css")) return "text/css";
        if(p.endsWith(".wasm")) return "application/wasm";
        if(p.endsWith(".json") || p.endsWith(".webmanifest")) return "application/json";
        if(p.endsWith(".svg")) return "image/svg+xml";
        if(p.endsWith(".png")) return "image/png";
        if(p.endsWith(".pdf")) return "application/pdf";
        if(p.endsWith(".woff2")) return "font/woff2";
        if(p.endsWith(".woff")) return "font/woff";
        return "application/octet-stream";
    }
}
