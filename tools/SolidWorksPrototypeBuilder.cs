using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using SolidWorks.Interop.sldworks;
using SolidWorks.Interop.swconst;

internal static class SolidWorksPrototypeBuilder
{
    private static readonly List<string> LogLines = new List<string>();

    private static void Log(string message)
    {
        string line = DateTime.Now.ToString("HH:mm:ss") + " " + message;
        LogLines.Add(line);
        Console.WriteLine(line);
    }

    private static void SaveLog(string path)
    {
        File.WriteAllLines(path, LogLines.ToArray());
    }

    private static void SelectTopPlane(ModelDoc2 model)
    {
        model.ClearSelection2(true);
        if (!model.Extension.SelectByID2("Top Plane", "PLANE", 0.0, 0.0, 0.0, false, 0, null, 0))
            throw new InvalidOperationException("Top Plane could not be selected.");
    }

    private static Feature CutEllipse(
        ModelDoc2 model,
        double centerX,
        double centerZ,
        double radiusX,
        double radiusZ,
        string featureName)
    {
        SelectTopPlane(model);
        model.SketchManager.InsertSketch(true);
        SketchSegment segment = model.SketchManager.CreateEllipse(
            centerX, centerZ, 0.0,
            centerX + radiusX, centerZ, 0.0,
            centerX, centerZ + radiusZ, 0.0);
        if (segment == null)
            throw new InvalidOperationException("Could not create ellipse for " + featureName);
        model.SketchManager.InsertSketch(true);
        Feature feature = model.FeatureManager.FeatureCut3(
            true, false, false,
            (int)swEndConditions_e.swEndCondThroughAllBoth,
            (int)swEndConditions_e.swEndCondBlind,
            0.01, 0.01,
            false, false, false, false,
            0.0, 0.0,
            false, false, false, false,
            false,
            true, true,
            false, false, false,
            (int)swStartConditions_e.swStartSketchPlane,
            0.0, false);
        if (feature == null)
            throw new InvalidOperationException("Cut feature failed: " + featureName);
        feature.Name = featureName;
        model.ClearSelection2(true);
        return feature;
    }

    private static Feature CutCircles(
        ModelDoc2 model,
        double[,] circles,
        string featureName)
    {
        SelectTopPlane(model);
        model.SketchManager.InsertSketch(true);
        for (int index = 0; index < circles.GetLength(0); index++)
        {
            SketchSegment segment = model.SketchManager.CreateCircleByRadius(
                circles[index, 0], circles[index, 1], 0.0, circles[index, 2]);
            if (segment == null)
                throw new InvalidOperationException("Could not create circle for " + featureName);
        }
        model.SketchManager.InsertSketch(true);
        Feature feature = model.FeatureManager.FeatureCut3(
            true, false, false,
            (int)swEndConditions_e.swEndCondThroughAllBoth,
            (int)swEndConditions_e.swEndCondBlind,
            0.01, 0.01,
            false, false, false, false,
            0.0, 0.0,
            false, false, false, false,
            false,
            true, true,
            false, false, false,
            (int)swStartConditions_e.swStartSketchPlane,
            0.0, false);
        if (feature == null)
            throw new InvalidOperationException("Cut feature failed: " + featureName);
        feature.Name = featureName;
        model.ClearSelection2(true);
        return feature;
    }

    private static void AddDesignProperties(ModelDoc2 model, string halfName)
    {
        CustomPropertyManager properties = model.Extension.CustomPropertyManager[""];
        properties.Add3("Prototype", (int)swCustomInfoType_e.swCustomInfoText,
            "Magic Conch electronics enclosure", (int)swCustomPropertyAddOption_e.swCustomPropertyReplaceValue);
        properties.Add3("Enclosure Half", (int)swCustomInfoType_e.swCustomInfoText,
            halfName, (int)swCustomPropertyAddOption_e.swCustomPropertyReplaceValue);
        properties.Add3("Nominal Wall", (int)swCustomInfoType_e.swCustomInfoText,
            "3.0 mm", (int)swCustomPropertyAddOption_e.swCustomPropertyReplaceValue);
        properties.Add3("Seam Clearance", (int)swCustomInfoType_e.swCustomInfoText,
            "0.4 mm total", (int)swCustomPropertyAddOption_e.swCustomPropertyReplaceValue);
        properties.Add3("Prototype Status", (int)swCustomInfoType_e.swCustomInfoText,
            "Fit-check before production print", (int)swCustomPropertyAddOption_e.swCustomPropertyReplaceValue);
    }

    private static void SaveNative(ModelDoc2 model, string path)
    {
        int errors = 0;
        int warnings = 0;
        bool saved = model.Extension.SaveAs(
            path,
            (int)swSaveAsVersion_e.swSaveAsCurrentVersion,
            (int)swSaveAsOptions_e.swSaveAsOptions_Silent,
            null,
            ref errors,
            ref warnings);
        if (!saved || errors != 0)
            throw new InvalidOperationException(
                "Save failed for " + path + " (errors=" + errors + ", warnings=" + warnings + ")");
        Log("Saved " + path + " (warnings=" + warnings + ")");
    }

    private static void ExportStl(ModelDoc2 model, string path)
    {
        int errors = 0;
        int warnings = 0;
        bool saved = model.Extension.SaveAs(
            path,
            (int)swSaveAsVersion_e.swSaveAsCurrentVersion,
            (int)swSaveAsOptions_e.swSaveAsOptions_Silent,
            null,
            ref errors,
            ref warnings);
        if (!saved || errors != 0)
            throw new InvalidOperationException(
                "STL export failed for " + path + " (errors=" + errors + ", warnings=" + warnings + ")");
        Log("Exported " + path + " (warnings=" + warnings + ")");
    }

    private static void BuildPart(
        SolidWorks.Interop.sldworks.SldWorks application,
        string inputStl,
        string outputPart,
        string halfName)
    {
        int errors = 0;
        int warnings = 0;
        Log("Opening " + inputStl);
        object importData = application.GetImportFileData(inputStl);
        ModelDoc2 model = application.LoadFile4(inputStl, "r", importData, ref errors);
        if (model == null)
            throw new InvalidOperationException(
                "SolidWorks could not open " + inputStl + " (errors=" + errors + ", warnings=" + warnings + ")");

        try
        {
            PartDoc part = (PartDoc)model;
            object[] bodies = part.GetBodies2((int)swBodyType_e.swSolidBody, true) as object[];
            if (bodies == null || bodies.Length == 0)
                throw new InvalidOperationException("Imported STL did not produce a solid body: " + inputStl);
            Log("Imported " + bodies.Length + " solid body/bodies for " + halfName);

            SaveNative(model, outputPart);
            AddDesignProperties(model, halfName);
            model.ForceRebuild3(false);
            model.ViewZoomtofit2();
            SaveNative(model, outputPart);
        }
        finally
        {
            application.CloseDoc(model.GetTitle());
        }
    }

    public static int Main(string[] args)
    {
        if (args.Length != 2)
        {
            Console.Error.WriteLine("Usage: SolidWorksPrototypeBuilder <prototype-directory> <log-file>");
            return 2;
        }

        string directory = Path.GetFullPath(args[0]);
        string logPath = Path.GetFullPath(args[1]);
        SolidWorks.Interop.sldworks.SldWorks application = null;
        int originalImportType = 0;
        int originalUnits = 0;
        bool originalMesh = false;
        bool preferencesCaptured = false;
        try
        {
            application = (SolidWorks.Interop.sldworks.SldWorks)Marshal.GetActiveObject("SldWorks.Application");
            application.Visible = true;
            application.CommandInProgress = true;
            Log("Connected to SolidWorks " + application.RevisionNumber());

            originalImportType = application.GetUserPreferenceIntegerValue(
                (int)swUserPreferenceIntegerValue_e.swImportStlVrmlModelType);
            originalUnits = application.GetUserPreferenceIntegerValue(
                (int)swUserPreferenceIntegerValue_e.swImportStlVrmlUnits);
            originalMesh = application.GetUserPreferenceToggle(
                (int)swUserPreferenceToggle_e.swVrmlStlImportAsPSMesh);
            preferencesCaptured = true;

            application.SetUserPreferenceIntegerValue(
                (int)swUserPreferenceIntegerValue_e.swImportStlVrmlModelType,
                (int)swImportStlVrmlModelType_e.swImportStlVrmlModelType_Solid);
            application.SetUserPreferenceIntegerValue(
                (int)swUserPreferenceIntegerValue_e.swImportStlVrmlUnits,
                (int)swLengthUnit_e.swMM);
            application.SetUserPreferenceToggle(
                (int)swUserPreferenceToggle_e.swVrmlStlImportAsPSMesh,
                true);
            application.SetUserPreferenceToggle(
                (int)swUserPreferenceToggle_e.swSTLBinaryFormat,
                true);

            BuildPart(
                application,
                Path.Combine(directory, "MagicConch_FrontHousing_print.stl"),
                Path.Combine(directory, "MagicConch_FrontHousing.SLDPRT"),
                "Front housing");
            BuildPart(
                application,
                Path.Combine(directory, "MagicConch_BackHousing_print.stl"),
                Path.Combine(directory, "MagicConch_BackHousing.SLDPRT"),
                "Back housing");
            Log("Prototype build completed successfully.");
            return 0;
        }
        catch (Exception exception)
        {
            Log("ERROR: " + exception);
            return 1;
        }
        finally
        {
            if (application != null)
            {
                if (preferencesCaptured)
                {
                    application.SetUserPreferenceIntegerValue(
                        (int)swUserPreferenceIntegerValue_e.swImportStlVrmlModelType,
                        originalImportType);
                    application.SetUserPreferenceIntegerValue(
                        (int)swUserPreferenceIntegerValue_e.swImportStlVrmlUnits,
                        originalUnits);
                    application.SetUserPreferenceToggle(
                        (int)swUserPreferenceToggle_e.swVrmlStlImportAsPSMesh,
                        originalMesh);
                }
                application.CommandInProgress = false;
            }
            SaveLog(logPath);
        }
    }
}
