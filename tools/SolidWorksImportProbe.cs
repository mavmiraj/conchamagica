using System;
using SolidWorks.Interop.sldworks;
using SolidWorks.Interop.swconst;

internal static class SolidWorksImportProbe
{
    public static int Main(string[] args)
    {
        if (args.Length != 2)
        {
            Console.Error.WriteLine("Usage: SolidWorksImportProbe <input-stl> <output-sldprt>");
            return 2;
        }
        SolidWorks.Interop.sldworks.SldWorks application = null;
        try
        {
            Type type = Type.GetTypeFromProgID("SldWorks.Application");
            application = (SolidWorks.Interop.sldworks.SldWorks)Activator.CreateInstance(type);
            application.Visible = false;
            application.CommandInProgress = true;
            application.SetUserPreferenceIntegerValue(
                (int)swUserPreferenceIntegerValue_e.swImportStlVrmlModelType,
                (int)swImportStlVrmlModelType_e.swImportStlVrmlModelType_Solid);
            application.SetUserPreferenceIntegerValue(
                (int)swUserPreferenceIntegerValue_e.swImportStlVrmlUnits,
                (int)swLengthUnit_e.swMM);
            application.SetUserPreferenceToggle(
                (int)swUserPreferenceToggle_e.swVrmlStlImportAsPSMesh,
                true);
            int errors = 0;
            int loadWarnings = 0;
            ModelDoc2 model = application.OpenDoc6(
                args[0],
                (int)swDocumentTypes_e.swDocPART,
                (int)swOpenDocOptions_e.swOpenDocOptions_Silent,
                "",
                ref errors,
                ref loadWarnings);
            if (model == null)
            {
                Console.Error.WriteLine("Import returned null; errors=" + errors);
                return 1;
            }
            int saveErrors = 0;
            int saveWarnings = 0;
            bool saved = model.Extension.SaveAs(
                args[1], 0, (int)swSaveAsOptions_e.swSaveAsOptions_Silent,
                null, ref saveErrors, ref saveWarnings);
            Console.WriteLine(
                "Imported and saved=" + saved + " loadErrors=" + errors +
                " saveErrors=" + saveErrors + " saveWarnings=" + saveWarnings);
            application.CloseDoc(model.GetTitle());
            return saved && saveErrors == 0 ? 0 : 1;
        }
        catch (Exception exception)
        {
            Console.Error.WriteLine(exception);
            return 1;
        }
        finally
        {
            if (application != null)
            {
                application.CommandInProgress = false;
                application.ExitApp();
            }
        }
    }
}
