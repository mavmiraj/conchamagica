using System;
using System.IO;
using SolidWorks.Interop.sldworks;
using SolidWorks.Interop.swconst;

internal static class SolidWorksNativeVerify
{
    public static int Main(string[] args)
    {
        if (args.Length == 0) return 2;
        SolidWorks.Interop.sldworks.SldWorks app = null;
        try
        {
            app = (SolidWorks.Interop.sldworks.SldWorks)Activator.CreateInstance(
                Type.GetTypeFromProgID("SldWorks.Application"));
            app.Visible = false;
            app.CommandInProgress = true;
            bool allValid = true;
            foreach (string path in args)
            {
                int errors = 0, warnings = 0;
                ModelDoc2 model = app.OpenDoc6(
                    Path.GetFullPath(path),
                    (int)swDocumentTypes_e.swDocPART,
                    (int)(swOpenDocOptions_e.swOpenDocOptions_Silent |
                          swOpenDocOptions_e.swOpenDocOptions_ReadOnly),
                    "", ref errors, ref warnings);
                if (model == null)
                {
                    Console.Error.WriteLine(Path.GetFileName(path) + ": open failed, errors=" + errors);
                    return 1;
                }
                PartDoc part = (PartDoc)model;
                object[] bodies = part.GetBodies2((int)swBodyType_e.swSolidBody, true) as object[];
                if (bodies == null || bodies.Length != 1)
                {
                    Console.Error.WriteLine(Path.GetFileName(path) + ": expected one solid body");
                    return 1;
                }
                Body2 body = (Body2)bodies[0];
                FaultEntity fault = body.Check3;
                bool valid = fault == null;
                double[] box = (double[])body.GetBodyBox();
                double[] mass = (double[])body.GetMassProperties(1.0);
                Console.WriteLine(
                    Path.GetFileName(path) +
                    ": solidBodies=1 valid=" + valid +
                    " dimensions_mm=" +
                    ((box[3] - box[0]) * 1000.0).ToString("F2") + " x " +
                    ((box[4] - box[1]) * 1000.0).ToString("F2") + " x " +
                    ((box[5] - box[2]) * 1000.0).ToString("F2") +
                    " volume_mm3=" + (mass[3] * 1.0e9).ToString("F1"));
                if (!valid)
                {
                    allValid = false;
                    Console.Write("  faults=" + fault.Count + " codes=");
                    for (int index = 0; index < fault.Count; index++)
                    {
                        if (index > 0) Console.Write(",");
                        Console.Write(fault.ErrorCode[index]);
                    }
                    Console.WriteLine();
                }
                app.CloseDoc(model.GetTitle());
            }
            return allValid ? 0 : 1;
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
