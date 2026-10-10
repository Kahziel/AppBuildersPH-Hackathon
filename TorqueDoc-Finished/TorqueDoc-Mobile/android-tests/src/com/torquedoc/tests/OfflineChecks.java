package com.torquedoc.tests;
import android.app.*;
import android.content.*;
import android.os.*;
import android.webkit.*;
import java.io.*;
import java.lang.reflect.Field;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

/** Separate test APK: the production APK contains no test interface or test code. */
public final class OfflineChecks extends Instrumentation {
    private volatile String result;
    private CountDownLatch resultReady=new CountDownLatch(1);
    private String asset="offline-check.js";
    public class ResultBridge {
        @JavascriptInterface public void complete(String value) {result=value;resultReady.countDown();}
        @JavascriptInterface public void progress(String value) {android.util.Log.i("TorqueDocAI",value);}
    }
    @Override public void onCreate(Bundle args) {super.onCreate(args);if(args!=null)asset=args.getString("script","offline-check.js");start();}
    @Override public void onStart() {
        Bundle output=new Bundle();
        try {
            Intent intent=new Intent(Intent.ACTION_MAIN).setClassName("com.torquedoc.app","com.torquedoc.app.MainActivity").addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            Activity activity=startActivitySync(intent);
            Field field=activity.getClass().getDeclaredField("web");field.setAccessible(true);
            WebView web=(WebView)field.get(activity);
            runOnMainSync(()->{web.addJavascriptInterface(new ResultBridge(),"TorqueDocTestResults");web.reload();});
            waitReady(web);
            String script;
            try(InputStream in=getContext().getAssets().open(asset)) {
                ByteArrayOutputStream bytes=new ByteArrayOutputStream();byte[] buffer=new byte[8192];int n;
                while((n=in.read(buffer))!=-1)bytes.write(buffer,0,n);
                script=new String(bytes.toByteArray(),StandardCharsets.UTF_8);
            }
            final String execute=script;
            runOnMainSync(()->web.evaluateJavascript(execute,null));
            if(!resultReady.await(asset.equals("offline-check.js")?90:900,TimeUnit.SECONDS))throw new Exception("Timed out waiting for WebView checks: "+asset);
            boolean passed=result.contains("\"passed\":true");
            if(passed && asset.equals("offline-check.js")) {
                runOnMainSync(web::reload);waitReady(web);
                CountDownLatch read=new CountDownLatch(1);String[] value=new String[1];
                runOnMainSync(()->web.evaluateJavascript("localStorage.getItem('torquedoc-android-acceptance')",v->{value[0]=v;read.countDown();}));
                if(!read.await(10,TimeUnit.SECONDS)||!"\"persisted-offline\"".equals(value[0]))throw new Exception("Storage did not survive native WebView reload");
                output.putString("storage_reload","PASS");
            }
            output.putString("report",result);
            finish(passed?Activity.RESULT_OK:Activity.RESULT_CANCELED,output);
        }catch(Throwable error){output.putString("error",android.util.Log.getStackTraceString(error));finish(Activity.RESULT_CANCELED,output);}
    }
    private void waitReady(WebView web)throws Exception {
        for(int i=0;i<120;i++) {
            CountDownLatch read=new CountDownLatch(1);String[] value=new String[1];
            runOnMainSync(()->web.evaluateJavascript("Boolean(window.TorqueDocWeb && document.querySelector('#machine-selector'))",v->{value[0]=v;read.countDown();}));
            read.await(2,TimeUnit.SECONDS);
            if("true".equals(value[0]))return;
            Thread.sleep(500);
        }
        throw new Exception("WebView app did not initialize");
    }
}
