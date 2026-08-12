using System;
using System.IO;
using SolidWorks.Interop.sldworks;
using SolidWorks.Interop.swconst;

internal static class SolidWorksExportPreviewMesh
{
    public static int Main(string[] args)
    {
        if (args.Length != 2) return 2;
        SolidWorks.Interop.sldworks.SldWorks app = null;
        try
        {
            app = (SolidWorks.Interop.sldworks.SldWorks)Activator.CreateInstance(
                Type.GetTypeFromProgID("SldWorks.Application"));
            app.Visible = false;
            app.CommandInProgress = true;
            app.SetUserPreferenceToggle(
                (int)swUserPreferenceToggle_e.swSTLBinaryFormat, true);
            int openErrors = 0, openWarnings = 0;
            ModelDoc2 model = app.OpenDoc6(
                Path.GetFullPath(args[0]),
                (int)swDocumentTypes_e.swDocPART,
                (int)(swOpenDocOptions_e.swOpenDocOptions_Silent |
                      swOpenDocOptions_e.swOpenDocOptions_ReadOnly),
                "", ref openErrors, ref openWarnings);
            if (model == null)
            {
                Console.Error.WriteLine("Open failed: " + openErrors);
                return 1;
            }
            int saveErrors = 0, saveWarnings = 0;
            bool saved = model.Extension.SaveAs(
                Path.GetFullPath(args[1]), 0,
                (int)swSaveAsOptions_e.swSaveAsOptions_Silent,
                null, ref saveErrors, ref saveWarnings);
            Console.WriteLine(
                "saved=" + saved + " openErrors=" + openErrors +
                " saveErrors=" + saveErrors + " saveWarnings=" + saveWarnings);
            app.CloseDoc(model.GetTitle());
            return saved && saveErrors == 0 ? 0 : 1;
        }
        catch (Exception exception)
        {
            Console.Error.WriteLine(exception);
            return 1;
        }
        finally
        {
            if (app != null)
            {
                app.CommandInProgress = false;
                app.ExitApp();
            }
        }
    }
}
